from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


class LLMProviderError(RuntimeError):
    pass


class LLMProviderUnavailable(LLMProviderError):
    pass


class LLMProviderMalformedOutput(LLMProviderError):
    pass


class JSONLLMProvider(Protocol):
    name: str
    model: str

    def generate_json(self, *, system: str, prompt: str, timeout_seconds: float | None = None) -> dict[str, Any]:
        ...


@dataclass
class LLMTelemetry:
    provider_name: str
    model: str
    request_count: int = 0
    retry_count: int = 0
    latency_seconds: float = 0.0
    input_tokens_estimate: int = 0
    output_tokens_estimate: int = 0
    estimated_cost: float = 0.0
    fallback_used: bool = False
    provider_available: bool = False
    errors: list[str] = field(default_factory=list)

    def add_request(self, *, prompt: str, output: str, latency: float, retries: int = 0) -> None:
        self.request_count += 1
        self.retry_count += retries
        self.latency_seconds += latency
        self.input_tokens_estimate += _estimate_tokens(prompt)
        self.output_tokens_estimate += _estimate_tokens(output)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["latency_seconds"] = round(float(payload["latency_seconds"]), 4)
        payload["estimated_cost"] = round(float(payload["estimated_cost"]), 6)
        return payload


class OpenAIChatJSONProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        temperature: float = 0.3,
        max_output_tokens: int = 4000,
        timeout_seconds: float = 90,
        max_retries: int = 2,
    ) -> None:
        self.name = "openai"
        self.model = model
        self.api_key = api_key or ""
        self.temperature = float(temperature)
        self.max_output_tokens = int(max_output_tokens)
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)

    @property
    def available(self) -> bool:
        return bool(self.api_key.strip())

    def generate_json(self, *, system: str, prompt: str, timeout_seconds: float | None = None) -> dict[str, Any]:
        if not self.available:
            raise LLMProviderUnavailable("OPENAI_API_KEY is missing")
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        encoded = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=encoded,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout_seconds or self.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                content = str(payload["choices"][0]["message"]["content"])
                return _parse_json_object(content)
            except urllib.error.HTTPError as exc:
                last_error = LLMProviderError(f"HTTPError_{exc.code}")
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2.0, 0.25 * (attempt + 1)))
            except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError, LLMProviderMalformedOutput) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2.0, 0.25 * (attempt + 1)))
        if isinstance(last_error, LLMProviderError):
            raise LLMProviderError(f"provider request failed: {last_error}") from last_error
        raise LLMProviderError(f"provider request failed: {type(last_error).__name__}")


class ArticleLLMService:
    def __init__(self, provider: JSONLLMProvider, *, telemetry: LLMTelemetry | None = None, timeout_seconds: float = 90) -> None:
        self.provider = provider
        self.telemetry = telemetry or LLMTelemetry(provider_name=provider.name, model=provider.model, provider_available=True)
        self.timeout_seconds = float(timeout_seconds)

    def write_article(self, *, topic: dict[str, Any], research_package: dict[str, Any]) -> dict[str, Any]:
        prompt = _writer_prompt(topic=topic, research_package=research_package)
        started = time.monotonic()
        try:
            payload = self.provider.generate_json(system=_writer_system_prompt(), prompt=prompt, timeout_seconds=self.timeout_seconds)
        except Exception as exc:
            self.telemetry.errors.append(f"writer:{type(exc).__name__}")
            raise
        latency = time.monotonic() - started
        self.telemetry.add_request(prompt=prompt, output=json.dumps(payload, ensure_ascii=False), latency=latency)
        return validate_writer_output(payload, topic=topic, research_package=research_package)

    def rewrite_section(self, *, section_id: str, section_html: str, issues: list[dict[str, Any]], context: dict[str, Any]) -> str:
        prompt = _rewrite_prompt(section_id=section_id, section_html=section_html, issues=issues, context=context)
        started = time.monotonic()
        try:
            payload = self.provider.generate_json(system=_rewrite_system_prompt(), prompt=prompt, timeout_seconds=self.timeout_seconds)
        except Exception as exc:
            self.telemetry.errors.append(f"rewrite:{type(exc).__name__}")
            raise
        latency = time.monotonic() - started
        self.telemetry.add_request(prompt=prompt, output=json.dumps(payload, ensure_ascii=False), latency=latency)
        rewritten = str(payload.get("section_html") or "")
        validate_rewrite_output(old=section_html, new=rewritten)
        return rewritten


class LLMSectionRewriteProvider:
    def __init__(self, service: ArticleLLMService) -> None:
        self.service = service

    def rewrite_section(self, *, section_id: str, section_html: str, issues: list[dict[str, Any]], context: dict[str, Any]) -> str:
        return self.service.rewrite_section(section_id=section_id, section_html=section_html, issues=issues, context=context)


def build_llm_service(config: dict[str, Any], *, allow_heuristic_fallback: bool = False) -> tuple[ArticleLLMService | None, dict[str, Any]]:
    llm_config = config.get("llm_provider") if isinstance(config.get("llm_provider"), dict) else {}
    provider_name = str(llm_config.get("provider") or "auto").strip().lower()
    model = str(os.getenv("OPENAI_MODEL") or llm_config.get("model") or "gpt-4o-mini").strip()
    timeout = float(llm_config.get("timeout_seconds", 90))
    telemetry = LLMTelemetry(provider_name="none", model=model, fallback_used=allow_heuristic_fallback, provider_available=False)
    if provider_name in {"auto", "openai"}:
        api_key_present = bool(os.getenv("OPENAI_API_KEY"))
        telemetry.provider_name = "openai"
        telemetry.provider_available = api_key_present
        status = {
            "provider": "openai",
            "model": model,
            "credentials_detected": api_key_present,
            "missing_environment": [] if api_key_present else ["OPENAI_API_KEY"],
            "provider_available": api_key_present,
            "allow_heuristic_fallback": allow_heuristic_fallback,
        }
        if not api_key_present:
            return None, {**status, "telemetry": telemetry.as_dict()}
        provider = OpenAIChatJSONProvider(
            api_key=os.getenv("OPENAI_API_KEY"),
            model=model,
            temperature=float(llm_config.get("temperature", 0.3)),
            max_output_tokens=int(float(llm_config.get("max_output_tokens", 4000))),
            timeout_seconds=timeout,
            max_retries=int(float(llm_config.get("max_retries", 2))),
        )
        return ArticleLLMService(provider, telemetry=telemetry, timeout_seconds=timeout), {**status, "telemetry": telemetry.as_dict()}
    return None, {
        "provider": provider_name,
        "model": model,
        "credentials_detected": False,
        "missing_environment": [f"{provider_name.upper()} provider is not implemented"],
        "provider_available": False,
        "allow_heuristic_fallback": allow_heuristic_fallback,
        "telemetry": telemetry.as_dict(),
    }


def validate_writer_output(payload: dict[str, Any], *, topic: dict[str, Any], research_package: dict[str, Any]) -> dict[str, Any]:
    required = ("title", "slug", "introduction", "sections", "conclusion", "faq", "citations", "metadata")
    missing = [key for key in required if key not in payload]
    if missing:
        raise LLMProviderMalformedOutput(f"writer output missing fields: {', '.join(missing)}")
    if str(payload.get("slug") or "").strip() != str(topic.get("slug") or "").strip():
        raise LLMProviderMalformedOutput("writer output slug mismatch")
    sections = payload.get("sections")
    if not isinstance(sections, list) or not sections:
        raise LLMProviderMalformedOutput("writer output has no sections")
    headings: list[str] = []
    source_urls = _source_urls_from_research(research_package)
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise LLMProviderMalformedOutput(f"section {index} is invalid")
        heading = str(section.get("heading") or "").strip()
        body = str(section.get("body") or "").strip()
        citations = section.get("citations")
        if not heading or not body:
            raise LLMProviderMalformedOutput(f"section {index} has empty heading or body")
        if not isinstance(citations, list) or not citations:
            raise LLMProviderMalformedOutput(f"section {index} has no citations")
        for url in citations:
            if str(url) not in source_urls:
                raise LLMProviderMalformedOutput("writer output contains citation outside validated source set")
        headings.append(heading.lower())
    if len(headings) != len(set(headings)):
        raise LLMProviderMalformedOutput("writer output has duplicate headings")
    if not isinstance(payload.get("faq"), list) or not payload.get("faq"):
        raise LLMProviderMalformedOutput("writer output has no faq")
    return payload


def validate_rewrite_output(*, old: str, new: str) -> None:
    if not new.strip():
        raise LLMProviderMalformedOutput("rewrite output is empty")
    old_headings = re.findall(r"<h[1-6]\b[^>]*>.*?</h[1-6]>", old, re.I | re.S)
    new_headings = re.findall(r"<h[1-6]\b[^>]*>.*?</h[1-6]>", new, re.I | re.S)
    if old_headings and old_headings[0] not in new_headings:
        raise LLMProviderMalformedOutput("rewrite changed heading hierarchy")
    for href in re.findall(r"href=['\"]([^'\"]+)['\"]", old, re.I):
        if href not in new:
            raise LLMProviderMalformedOutput("rewrite removed citation or internal link")


def render_writer_output(payload: dict[str, Any], *, canonical_url: str) -> tuple[str, str, list[dict[str, Any]]]:
    title = str(payload["title"])
    description = str(payload.get("metadata", {}).get("description") or f"{title} buyer review.")
    sections_html: list[str] = []
    claim_mapping: list[dict[str, Any]] = []
    for index, section in enumerate(payload["sections"]):
        section_id = re.sub(r"[^a-z0-9]+", "-", str(section["heading"]).lower()).strip("-") or f"section-{index + 1}"
        citations = [str(url) for url in section.get("citations", [])]
        links = " ".join(f'<a href="{_escape(url)}">[{idx + 1}]</a>' for idx, url in enumerate(citations))
        sections_html.append(f'<section id="{section_id}"><h2>{_escape(section["heading"])}</h2><p>{_escape(section["body"])}</p><p class="citations">{links}</p></section>')
        for claim in section.get("claims", []) if isinstance(section.get("claims"), list) else []:
            claim_mapping.append({"claim": str(claim), "source_url": citations[0] if citations else "", "importance": "important"})
    faq_items = payload.get("faq", [])
    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": str(item.get("question")), "acceptedAnswer": {"@type": "Answer", "text": str(item.get("answer"))}}
            for item in faq_items if isinstance(item, dict)
        ],
    }
    article_schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "author": {"@type": "Person", "name": "Smile AI Review Hub Editorial Team"},
        "mainEntityOfPage": canonical_url,
    }
    faq_html = "\n".join(f"<details><summary>{_escape(item.get('question', ''))}</summary><p>{_escape(item.get('answer', ''))}</p></details>" for item in faq_items if isinstance(item, dict))
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{_escape(title)}</title>
  <meta name="description" content="{_escape(description)}">
  <link rel="canonical" href="{_escape(canonical_url)}">
  <script type="application/ld+json">{json.dumps(article_schema, ensure_ascii=False)}</script>
  <script type="application/ld+json">{json.dumps(faq_schema, ensure_ascii=False)}</script>
</head>
<body>
<article>
<h1>{_escape(title)}</h1>
<section id="affiliate-disclosure"><h2>Affiliate disclosure</h2><p>Some links may be affiliate links. We may earn a commission at no extra cost to readers.</p></section>
<section id="introduction"><h2>Introduction</h2><p>{_escape(payload['introduction'])}</p></section>
{''.join(sections_html)}
<section id="faq"><h2>FAQ</h2>{faq_html}</section>
<section id="conclusion"><h2>Conclusion</h2><p>{_escape(payload['conclusion'])}</p></section>
</article>
</body>
</html>
"""
    markdown = f"# {title}\n\n{payload['introduction']}\n\n" + "\n\n".join(f"## {section['heading']}\n\n{section['body']}" for section in payload["sections"]) + f"\n\n## Conclusion\n\n{payload['conclusion']}\n"
    return html_doc, markdown, claim_mapping


def _writer_system_prompt() -> str:
    return (
        "You are a production editorial writer. Return strict JSON only. "
        "Use only the provided sources. Do not invent pricing, dates, partnerships, or unsupported claims."
    )


def _rewrite_system_prompt() -> str:
    return (
        "You are a section rewrite provider. Return strict JSON only with section_html. "
        "Rewrite only the provided section and preserve headings, citations, links, metadata references, and schema-related text."
    )


def _writer_prompt(*, topic: dict[str, Any], research_package: dict[str, Any]) -> str:
    safe_research = {
        "keyword": research_package.get("keyword"),
        "slug": research_package.get("slug"),
        "outline": research_package.get("outline"),
        "faq": research_package.get("faq"),
        "entities": research_package.get("entities"),
        "sources": {"verified_sources": _source_urls_from_research(research_package)},
        "quality": research_package.get("quality"),
    }
    contract = {
        "title": "string",
        "slug": topic.get("slug"),
        "introduction": "string",
        "sections": [{"heading": "string", "body": "string", "citations": ["source url"], "claims": ["source-backed claim"]}],
        "conclusion": "string",
        "faq": [{"question": "string", "answer": "string"}],
        "citations": ["source url"],
        "metadata": {"description": "string", "language": "en"},
    }
    return json.dumps({"topic": topic, "research_package": safe_research, "required_json_contract": contract}, ensure_ascii=False)


def _rewrite_prompt(*, section_id: str, section_html: str, issues: list[dict[str, Any]], context: dict[str, Any]) -> str:
    return json.dumps({"section_id": section_id, "section_html": section_html, "issues": issues, "context": context, "required_json_contract": {"section_html": "rewritten section html only"}}, ensure_ascii=False)


def _source_urls_from_research(research_package: dict[str, Any]) -> list[str]:
    sources = research_package.get("sources") if isinstance(research_package.get("sources"), dict) else {}
    rows = sources.get("verified_sources") if isinstance(sources.get("verified_sources"), list) else []
    urls = [str(row.get("url") or row.get("source_url") or "") for row in rows if isinstance(row, dict)]
    return [url for url in urls if url.startswith(("http://", "https://"))]


def _parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMProviderMalformedOutput("provider returned non-json output") from exc
    if not isinstance(payload, dict):
        raise LLMProviderMalformedOutput("provider returned non-object json")
    return payload


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 4))


def _escape(value: Any) -> str:
    import html

    return html.escape(str(value or ""), quote=True)
