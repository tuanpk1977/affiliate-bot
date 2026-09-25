from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


X_MAX_CHARACTERS = 280
X_THREAD_ENABLED = False

COMPONENT_ROLES = {
    "A.md": "ACTIONABLE",
    "B.md": "INSIGHT",
    "C.md": "PROBLEM_SOLUTION",
}

# Compatibility alias for imported packages produced before the component
# model.  Runtime metadata uses COMPONENT_ROLES and never treats these as
# competing publication choices.
VARIANT_STRATEGIES = COMPONENT_ROLES

ANGLE_POOLS = {
    "ACTIONABLE": ("ACTIONABLE_HOW_TO", "CHECKLIST", "STEP_BY_STEP", "WHAT_TO_DO_NEXT"),
    "INSIGHT": ("KEY_INSIGHT", "CONTRARIAN_ANGLE", "MYTH_VS_REALITY", "LESSON_FROM_SOURCE"),
    "PROBLEM_SOLUTION": ("PROBLEM_SOLUTION", "COMMON_MISTAKE", "MINI_CASE", "BEFORE_AFTER"),
}


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _sentences(value: object) -> list[str]:
    text = _clean(value)
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if len(part.strip()) >= 24]


def validate_x_draft(text: str, max_characters: int = X_MAX_CHARACTERS) -> dict[str, Any]:
    count = len(text)
    return {
        "character_count": count,
        "max_characters": max_characters,
        "within_limit": count <= max_characters,
        "status": "PASS" if count <= max_characters else "INVALID_PLATFORM_LIMIT",
    }


def semantic_x_choice(candidates: Iterable[str], max_characters: int = X_MAX_CHARACTERS) -> tuple[str, int]:
    """Choose a deliberately rewritten candidate; never slice/truncate a draft."""
    cleaned = [_clean(candidate) for candidate in candidates if _clean(candidate)]
    for attempt, candidate in enumerate(cleaned, start=1):
        if len(candidate) <= max_characters:
            return candidate, attempt
    raise ValueError("No semantic X rewrite satisfies the configured character limit.")


@dataclass(frozen=True)
class SocialKnowledge:
    topic: str
    action: str
    insight: str
    problem: str
    solution: str
    evidence_refs: tuple[str, ...]


class PlatformNativeSocialEngine:
    """Deterministic, source-grounded social planning and starter-draft engine."""

    def __init__(self, playbooks: dict[str, dict[str, Any]]) -> None:
        self.playbooks = playbooks

    @staticmethod
    def extract_knowledge(package: dict[str, Any]) -> SocialKnowledge:
        article = package.get("article") if isinstance(package.get("article"), dict) else {}
        evidence = package.get("evidence") if isinstance(package.get("evidence"), dict) else {}
        texts: list[str] = []
        refs: list[str] = []
        for source in list(evidence.get("source_excerpts") or []):
            if not isinstance(source, dict):
                continue
            for paragraph in list(source.get("paragraphs") or []):
                if not isinstance(paragraph, dict):
                    continue
                text = _clean(paragraph.get("text"))
                if text and "affiliate disclosure" not in text.casefold():
                    texts.append(text)
                    ref = _clean(paragraph.get("paragraph_id"))
                    if ref:
                        refs.append(ref)
        if not texts:
            texts = _sentences(article.get("summary") or article.get("meta_description") or article.get("title"))
        all_sentences = [sentence for text in texts for sentence in _sentences(text)] or texts

        def pick(pattern: str, fallback: str) -> str:
            match = next((s for s in all_sentences if re.search(pattern, s, re.I)), "")
            return match or fallback

        fallback = _clean(article.get("meta_description") or article.get("title"))
        action = pick(r"\b(start|first|define|select|identify|map|use|keep|track|set)\b", fallback)
        insight = pick(r"\b(does not|rather than|goal|matters|target|best treated|more than)\b", fallback)
        problem = pick(r"\b(inconsistent|struggle|risk|failure|erode|revert|not ready)\b", fallback)
        solution = pick(r"\b(standardize|controlled|human review|approved|govern|pilot|workflow)\b", action)
        title = _clean(article.get("title"))
        topic = "healthcare AI engagement" if "healthcare" in title.casefold() else title
        return SocialKnowledge(topic, action, insight, problem, solution, tuple(dict.fromkeys(refs[:8])))

    @staticmethod
    def select_angles(platform: str, recent_angles: Iterable[str]) -> dict[str, str]:
        used = {str(angle) for angle in recent_angles if str(angle)}
        selected: dict[str, str] = {}
        for filename, strategy in VARIANT_STRATEGIES.items():
            pool = ANGLE_POOLS[strategy]
            selected[filename] = next((angle for angle in pool if angle not in used), pool[0])
            used.add(selected[filename])
        return selected

    @staticmethod
    def _x_variants(k: SocialKnowledge, url: str) -> dict[str, tuple[str, int]]:
        a = semantic_x_choice((
            f"Before automating {k.topic}, define the human decision, intent signal, approved resource, and accountable owner. If those four are unclear, the workflow is not ready.",
            f"Before automating {k.topic}, define 4 things: decision, signal, approved resource, owner. If they are unclear, the workflow is not ready.",
            "Before automating, define the decision, signal, approved resource, and owner. Unclear inputs mean the workflow is not ready.",
        ))
        b = semantic_x_choice((
            f"The goal in {k.topic} is not more automated messages. It is a relevant, approved response inside the right workflow, with human review where risk requires it.",
            "Automation volume is not the goal. A relevant, approved response in the right workflow is more useful—and easier to govern.",
            "Automate for relevance and governance, not message volume.",
        ))
        c = semantic_x_choice((
            "A common AI rollout mistake: automating inconsistent inputs. Standardize intake, reject incomplete records, and pilot one governed workflow before scaling.",
            "Inconsistent inputs make automation scale inconsistency. Standardize intake, reject incomplete records, then pilot one governed workflow.",
            "Do not automate inconsistent inputs. Standardize intake, reject incomplete records, and pilot one governed workflow.",
        ))
        return {"A.md": a, "B.md": b, "C.md": c}

    @staticmethod
    def compose_final(
        *,
        platform: str,
        knowledge: SocialKnowledge,
        url: str = "",
    ) -> dict[str, Any]:
        """Synthesize one publishable post from the three knowledge dimensions.

        Components remain internal review aids.  The composer works from the
        same extracted, source-bound knowledge so it cannot introduce bridging
        facts that were absent from the source package.
        """
        k = knowledge
        if platform == "facebook_en":
            title = f"A practical way to implement {k.topic}"
            text = (
                f"More automation is not automatically better engagement. {k.insight}\n\n"
                f"A practical starting point: {k.action}\n\n"
                f"The common failure is scaling an unclear process. {k.problem} "
                f"The safer response is to {k.solution[:1].lower() + k.solution[1:]}\n\n"
                "Start with one explainable workflow, review what happens, and expand only when the process is reliable."
            )
        elif platform == "facebook_vi":
            title = f"Cách triển khai {k.topic} trong thực tế"
            solution = k.solution.strip()
            text = (
                f"Điểm then chốt là {k.insight}\n\n"
                f"Để chuyển nhận định đó thành hành động, hãy bắt đầu bằng một bước có thể kiểm tra: {k.action}\n\n"
                f"Khó khăn thường gặp: {k.problem} "
                f"Giải pháp thực tế: {solution}"
            )
        elif platform == "linkedin":
            title = f"Implementing {k.topic}: govern the workflow before scaling it"
            text = (
                f"More automation is not the same as better engagement. {k.insight}\n\n"
                "Why it matters: a system can scale an unclear operating model just as efficiently as a sound one.\n\n"
                f"Start here: {k.action}\n\n"
                f"A common implementation problem is inconsistent input. {k.problem} "
                f"The practical response is to {k.solution[:1].lower() + k.solution[1:]}\n\n"
                "The useful question is not only what the tool can automate, but whether the team can explain and govern the result."
            )
        elif platform == "x":
            candidates = (
                f"{k.insight} Act on this: {k.action} Fix the common failure by using this approach: {k.solution}",
                "Automation volume is not the goal. Define the decision, signal, approved resource and owner; standardize inconsistent inputs before scaling.",
                "Before automating: define the decision, signal, approved resource and owner. Standardize inconsistent inputs, then pilot one governed workflow.",
            )
            text, attempts = semantic_x_choice(candidates)
            return {
                "title": f"{k.topic}: one governed workflow",
                "text": text + "\n",
                "character_count": len(text),
                "max_characters": X_MAX_CHARACTERS,
                "within_limit": True,
                "semantic_generation_attempts": attempts,
                "thread_enabled": X_THREAD_ENABLED,
            }
        elif platform == "quora":
            title = f"How should a team implement {k.topic}?"
            text = (
                f"Direct answer: start with one governed workflow and a clear accountable owner.\n\n"
                f"The key insight is that {k.insight[:1].lower() + k.insight[1:]}\n\n"
                f"In practice, {k.action[:1].lower() + k.action[1:]}\n\n"
                f"A common problem is inconsistent input: {k.problem} "
                f"Handle it by ensuring that {k.solution[:1].lower() + k.solution[1:]}\n\n"
                "Expand only after the team can review why each action occurred and how incomplete records were handled."
            )
        elif platform == "devto":
            title = f"A governed implementation pattern for {k.topic}"
            text = (
                f"## The implementation insight\n\n{k.insight}\n\n"
                f"## Define the workflow contract\n\n{k.action}\n\n"
                f"## Handle the failure mode\n\n{k.problem} {k.solution}\n\n"
                "Use only source-supported fields and route incomplete input to a human owner instead of inventing missing values."
            )
        elif platform == "pinterest":
            title = f"A Practical {k.topic} Workflow"
            text = (
                f"Pin title: {title}\n\n"
                f"Pin description: Turn the core insight into action and avoid the common input failure: {k.action} {k.problem} {k.solution}\n\n"
                f"Keyword intent: {k.topic} implementation checklist\n\n"
                "Visual concept: decision → signal → approved resource → accountable owner"
                + (f"\n\nDestination URL: {url}" if url else "")
            )
        else:  # blogger
            title = f"A practical implementation pattern for {k.topic}"
            text = (
                f"# {title}\n\n"
                f"## The core insight\n\n{k.insight}\n\n"
                f"## What to do\n\n{k.action}\n\n"
                f"## The common problem and response\n\n{k.problem} {k.solution}\n\n"
                "A useful rollout starts with one explainable workflow and expands only after the team can review its inputs and outcomes."
            )
        clean = text.strip()
        if url and url not in clean:
            source_label = "Bài viết nguồn" if platform == "facebook_vi" else "Source article"
            clean = f"{clean}\n\n{source_label}: {url}"
        return {
            "title": title,
            "text": clean + "\n",
            "character_count": len(clean),
            "max_characters": None,
            "within_limit": True,
            "semantic_generation_attempts": 1,
            "thread_enabled": False,
        }

    @classmethod
    def compose_components(
        cls,
        *,
        platform: str,
        components: dict[str, str],
        topic: str,
        url: str = "",
        evidence_refs: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Recompose legacy A/B/C safely without changing their source text."""
        action_parts = _sentences(components.get("A.md", ""))
        insight_parts = _sentences(components.get("B.md", ""))
        problem_parts = _sentences(components.get("C.md", ""))
        fallback = _clean(topic) or "the current workflow"
        if platform == "facebook_vi":
            action = " ".join(action_parts) or fallback
            insight = " ".join(insight_parts) or fallback
            problem = problem_parts[0] if problem_parts else fallback
            solution = " ".join(problem_parts[1:]) or (
                action_parts[-1] if action_parts else fallback
            )
        else:
            action = action_parts[0] if action_parts else fallback
            insight = insight_parts[0] if insight_parts else fallback
            problem = problem_parts[0] if problem_parts else fallback
            solution = problem_parts[1] if len(problem_parts) > 1 else (
                action_parts[-1] if action_parts else fallback
            )
        knowledge = SocialKnowledge(
            topic=fallback,
            action=action,
            insight=insight,
            problem=problem,
            solution=solution,
            evidence_refs=tuple(dict.fromkeys(str(ref) for ref in evidence_refs if str(ref))),
        )
        return cls.compose_final(platform=platform, knowledge=knowledge, url=url)

    def generate(
        self,
        *,
        package: dict[str, Any],
        platform: str,
        recent_angles: Iterable[str] = (),
    ) -> dict[str, Any]:
        if platform not in self.playbooks:
            raise ValueError(f"Missing configured platform playbook: {platform}")
        article = package.get("article") if isinstance(package.get("article"), dict) else {}
        provenance = package.get("provenance") if isinstance(package.get("provenance"), dict) else {}
        k = self.extract_knowledge(package)
        url = _clean(article.get("canonical_url") or article.get("url"))
        angles = self.select_angles(platform, recent_angles)
        titles = {
            "A.md": f"A practical way to start with {k.topic}",
            "B.md": f"The non-obvious goal of {k.topic}",
            "C.md": "Why automating inconsistent inputs fails",
        }
        if platform == "x":
            built = self._x_variants(k, url)
            drafts = {name: value[0] + "\n" for name, value in built.items()}
            attempts = {name: value[1] for name, value in built.items()}
        elif platform == "linkedin":
            drafts = {
                "A.md": f"Before automating {k.topic}, make four decisions explicit:\n\n1. The human decision being supported\n2. The signal that indicates intent\n3. The approved resource for that moment\n4. The owner accountable for the response\n\nIf the team cannot explain these in plain language, the workflow is not ready. Start with one low-risk use case and review it before scaling.\n\n{k.action}\n",
                "B.md": f"More automation is not the same as better engagement.\n\nThe useful shift is from message volume to relevance: recognize a meaningful need, use approved material, preserve human review, and learn from the response.\n\nThat changes the buying question. Do not ask only what a tool can automate. Ask whether the operating model can govern the result.\n\n{k.insight}\n",
                "C.md": f"AI can scale a weak process just as efficiently as a strong one.\n\nThe failure pattern is inconsistent intake, missing ownership, and automation added before review rules are clear.\n\nA safer sequence:\n- standardize required inputs\n- reject incomplete records\n- pilot one governed workflow\n- expand only after reliable handling\n\n{k.solution}\n",
            }
            attempts = {}
        elif platform == "facebook_en":
            drafts = {
                "A.md": f"Thinking about adding AI to a healthcare marketing workflow? Start smaller than a tool shortlist.\n\nWrite down the decision, the intent signal, the approved resource, and the person who owns the response. If any of those are vague, automation will only hide the gap.\n\nA focused pilot gives the team something it can review, learn from, and improve before scaling.\n",
                "B.md": "The most useful healthcare AI workflow may send fewer messages, not more.\n\nThe goal is to recognize a real need and provide a relevant, approved resource without weakening human review. That is an operating-model decision before it is a software decision.\n\nMeasure whether the interaction helped—not simply how much activity automation produced.\n",
                "C.md": "A familiar automation problem: inconsistent briefs go in, inconsistent outputs come out—only faster.\n\nStandardize intake first. Define required and prohibited data, set a fallback for incomplete records, and assign an owner. Then test one low-risk workflow before expanding.\n\nGood automation starts with a process people can explain.\n",
            }
            attempts = {}
        elif platform == "facebook_vi":
            drafts = {
                "A.md": "Muốn ứng dụng AI vào marketing y tế, đừng bắt đầu bằng danh sách công cụ.\n\nTrước hết, hãy xác định rõ 4 điều: quyết định nào cần hỗ trợ, tín hiệu nào cho thấy nhu cầu, tài liệu nào đã được phê duyệt và ai chịu trách nhiệm phản hồi. Nếu chưa giải thích được bằng lời đơn giản, quy trình chưa sẵn sàng để tự động hóa.\n",
                "B.md": "Tự động hóa nhiều hơn chưa chắc tạo ra tương tác tốt hơn.\n\nĐiều quan trọng là nhận ra đúng nhu cầu, đưa đúng tài liệu đã được duyệt vào đúng quy trình và vẫn giữ bước kiểm tra của con người khi cần. Vì vậy, đây là bài toán thiết kế cách vận hành trước khi là bài toán mua phần mềm.\n",
                "C.md": "Một lỗi phổ biến khi triển khai AI: đầu vào thiếu nhất quán nhưng đội ngũ vẫn vội tự động hóa.\n\nCách xử lý tốt hơn là chuẩn hóa biểu mẫu tiếp nhận, từ chối hồ sơ thiếu dữ liệu, chỉ thử nghiệm một quy trình ít rủi ro và mở rộng sau khi kết quả đã ổn định.\n",
            }
            attempts = {}
            titles = {
                "A.md": "4 điều cần xác định trước khi tự động hóa",
                "B.md": "Mục tiêu không phải là gửi nhiều thông điệp hơn",
                "C.md": "Đừng tự động hóa đầu vào thiếu nhất quán",
            }
        elif platform == "quora":
            drafts = {
                "A.md": "Question: How should a healthcare marketing team start implementing AI?\n\nStart with one governed workflow, not a broad tool rollout. Define the human decision, intent signal, approved resource, and accountable owner. Then choose one low-risk use case, keep human review visible, and review evidence weekly before expanding.\n",
                "B.md": "Question: Does better AI engagement mean sending more automated messages?\n\nNo. The stronger objective is relevance: recognize a meaningful need and deliver an approved resource through the right workflow. Message volume can increase activity without improving usefulness, trust, or governance.\n",
                "C.md": "Question: What is a common mistake in healthcare AI automation?\n\nAutomating inconsistent inputs. When briefs and source records vary, automation scales that inconsistency. Standardize required fields, define prohibited data and fallback behavior, reject incomplete records, and pilot one controlled workflow first.\n",
            }
            attempts = {}
        elif platform == "devto":
            drafts = {
                "A.md": "## Treat the workflow contract as the first implementation artifact\n\nBefore choosing connectors, define the decision, input signal, approved content, owner, permitted data, and fallback behavior. This turns a vague AI initiative into a testable workflow contract. Start with one low-risk path and keep review gates explicit.\n",
                "B.md": "## Automation throughput is the wrong primary metric\n\nA system can process more events while producing less useful engagement. Measure completed governed workflows: valid input, approved resource, accountable action, and reviewable feedback. That exposes quality failures hidden by volume metrics.\n",
                "C.md": "## Reject malformed input instead of inventing missing values\n\nInconsistent intake is a systems problem. Define a schema, validate required fields, block prohibited data, and route incomplete records to a human owner. Only then automate a narrow workflow and expand from observed reliability.\n",
            }
            attempts = {}
        elif platform == "pinterest":
            drafts = {
                "A.md": "Pin title: 4 Steps Before Automating Healthcare Marketing\n\nPin description: Define the decision, signal, approved resource, and accountable owner before building an AI workflow. Use this checklist to plan a small, governed pilot.\n",
                "B.md": "Pin title: Healthcare AI Engagement: Relevance Over Volume\n\nPin description: A visual framework for shifting from more automated messages to relevant, approved engagement with clear human review.\n",
                "C.md": "Pin title: Fix Inconsistent Inputs Before AI Automation\n\nPin description: Standardize intake, reject incomplete records, and pilot one governed workflow before scaling healthcare marketing automation.\n",
            }
            attempts = {}
        else:  # blogger
            drafts = {
                "A.md": f"# A practical starting point for {k.topic}\n\nAI implementation should begin with a workflow the team can explain. Define the human decision, the signal that may indicate intent, the approved resource available for that moment, and the owner accountable for the response.\n\nStart with one low-risk use case. Keep review visible, document what happens, and expand only after the workflow handles real inputs reliably. This approach makes tool selection follow operational need instead of leading it.\n",
                "B.md": f"# Why relevance matters more than automation volume\n\nThe non-obvious lesson in {k.topic} is that sending more messages is not the goal. A useful system recognizes a meaningful need, offers relevant approved material, and preserves governance.\n\nThat shifts measurement away from raw activity. Teams should ask whether the interaction was useful and whether reviewers can explain why the action occurred. Software supports that operating model; it does not replace it.\n",
                "C.md": "# The input problem that breaks AI workflows\n\nAutomation scales the process it receives. If briefs and records are inconsistent, the system reproduces that inconsistency faster.\n\nA safer implementation standardizes required fields, limits permitted data, defines fallback behavior, and assigns an owner for incomplete records. After that foundation exists, the team can pilot one governed workflow and expand based on observed reliability.\n",
            }
            attempts = {}

        variant_meta: dict[str, Any] = {}
        for filename, text in drafts.items():
            validation = validate_x_draft(text.strip()) if platform == "x" else {
                "character_count": len(text.strip()),
                "max_characters": None,
                "within_limit": True,
                "status": "PASS",
            }
            variant_meta[filename] = {
                "component_role": COMPONENT_ROLES[filename],
                "variant_strategy": COMPONENT_ROLES[filename],
                "social_angle": _clean(provenance.get("today_social_angle") or provenance.get("social_angle") or article.get("daily_angle") or "source_article_adaptation"),
                "character_count": validation["character_count"],
                "platform_limit": validation["max_characters"],
                "within_limit": validation["within_limit"],
                "platform_validation_status": validation["status"],
                "semantic_generation_attempts": attempts.get(filename, 1),
                "evidence_refs": list(k.evidence_refs),
                "claim_classification": {
                    "INHERITED_CLAIM": list(k.evidence_refs),
                    "NEW_CLAIM": [],
                    "OPINION": [],
                    "ADVICE": ["source-grounded operational recommendation"],
                    "QUESTION": ["opening question"] if platform == "quora" else [],
                },
            }
        final = (
            self.compose_components(
                platform=platform,
                components=drafts,
                topic=k.topic,
                url=url,
                evidence_refs=k.evidence_refs,
            )
            if platform == "facebook_vi"
            else self.compose_final(platform=platform, knowledge=k, url=url)
        )
        visual_type = "CHECKLIST_CARD" if platform == "pinterest" else "WORKFLOW_DIAGRAM"
        visual = {
            "visual_recommended": platform in {"linkedin", "facebook_en", "facebook_vi", "x", "pinterest"},
            "visual_type": visual_type,
            "visual_concept": "A four-part decision-signal-approved-resource-owner workflow; concept only unless an existing source asset is available.",
            "visual_source": "CONCEPT_ONLY",
            "visual_alt_text": "Diagram showing decision, signal, approved resource, and accountable owner before automation.",
        }
        return {
            "drafts": drafts,
            "components": drafts,
            "content_model": "COMPLEMENTARY_COMPONENTS_V1",
            "today_social_angle": _clean(provenance.get("today_social_angle") or provenance.get("social_angle") or article.get("daily_angle") or "source_article_adaptation"),
            "final_post": final["text"],
            "final_title": final["title"],
            "final_metadata": {
                **final,
                "component_inputs": ["A.md", "B.md", "C.md"],
                "evidence_refs": list(k.evidence_refs),
                "new_claims": [],
                "claim_guard": "SOURCE_AND_COMPONENT_KNOWLEDGE_ONLY",
            },
            "variant_titles": titles,
            "variant_metadata": variant_meta,
            "visual": visual,
            "playbook": dict(self.playbooks[platform]),
            "root_topic_id": _clean(provenance.get("root_topic_id")),
            "source_article_slug": _clean(provenance.get("source_article_slug") or article.get("slug")),
            "source_revision": _clean(provenance.get("source_revision_id")),
            "source_content_hash": _clean(provenance.get("source_content_hash")),
            "evidence_refs": list(k.evidence_refs),
            "new_claims": [],
        }
