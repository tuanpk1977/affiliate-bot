from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any

REQUIRED_REPORTS = [
    "architecture-report.md",
    "seo-audit.md",
    "content-audit.md",
    "technical-audit.md",
    "schema-audit.md",
    "quality-audit.md",
    "entity-audit.md",
    "authority-audit.md",
    "affiliate-audit.md",
    "performance-audit.md",
    "migration-plan.md",
    "rollback-plan.md",
    "ai-governance.md",
    "feature-flags.json",
]


def build_governance_report(output_dir: Path) -> Path:
    content = """# AI Governance

## Purpose
- Establish a single source of truth for each capability.
- Prefer refactor and reuse over creating duplicate modules.
- Keep all new features behind feature flags.
- Preserve backward compatibility with current workflows.
- Pair every new module with documentation and tests.

## Governance Rules
1. Do not create a new module when an equivalent module already exists.
2. Prefer refactoring the existing module before adding a new one.
3. Every new feature must be toggleable with a feature flag.
4. Preserve backward compatibility for the existing publishing workflow.
5. Require tests and documentation for every new module.
"""
    path = output_dir / "ai-governance.md"
    path.write_text(content, encoding="utf-8")
    return path


def build_feature_flags(output_dir: Path) -> Path:
    payload = {
        "seo_intelligence_engine": {"enabled": False, "description": "Enable advanced feedback integration"},
        "content_engine_v2": {"enabled": False, "description": "Enable new blueprint engine"},
        "schema_engine_v2": {"enabled": False, "description": "Enable advanced schema generation"},
        "affiliate_optimization": {"enabled": False, "description": "Enable affiliate performance scoring"},
    }
    path = output_dir / "feature-flags.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_report(output_dir: Path, name: str, title: str, sections: List[str]) -> Path:
    body = [f"# {title}", "", *sections, ""]
    path = output_dir / name
    path.write_text("\n".join(body), encoding="utf-8")
    return path


def generate_reports(output_dir: Path | None = None) -> List[Path]:
    target_dir = output_dir or Path(__file__).resolve().parents[1] / "reports"
    target_dir.mkdir(parents=True, exist_ok=True)

    governance_path = build_governance_report(target_dir)
    feature_flags_path = build_feature_flags(target_dir)

    reports = [
        governance_path,
        feature_flags_path,
        _write_report(
            target_dir,
            "architecture-report.md",
            "Architecture Report",
            [
                "## Summary",
                "- Audit the current publishing, topic scoring, and site generation stack.",
                "- Identify modules that should be reused instead of duplicated.",
                "- Preserve the current workflow while preparing for future scale.",
            ],
        ),
        _write_report(
            target_dir,
            "seo-audit.md",
            "SEO Audit",
            [
                "## Summary",
                "- Review canonical routing, sitemap, robots, and IndexNow workflow.",
                "- Check for duplicate content, thin content, and cannibalization risks.",
                "- Prioritize high-impression, low-CTR opportunities.",
            ],
        ),
        _write_report(
            target_dir,
            "content-audit.md",
            "Content Audit",
            [
                "## Summary",
                "- Review article quality, topical depth, internal link coverage, and affiliate CTA placement.",
                "- Identify pages that are strong candidates for upgrade before new publishing.",
            ],
        ),
        _write_report(
            target_dir,
            "technical-audit.md",
            "Technical Audit",
            [
                "## Summary",
                "- Review module boundaries, serialized data, and build pipeline safety.",
                "- Confirm that the current publish path remains backward compatible.",
            ],
        ),
        _write_report(
            target_dir,
            "schema-audit.md",
            "Schema Audit",
            [
                "## Summary",
                "- Review article, review, FAQ, breadcrumb, and organization schema coverage.",
                "- Ensure structured data remains consistent with the live content model.",
            ],
        ),
        _write_report(
            target_dir,
            "quality-audit.md",
            "Quality Audit",
            [
                "## Summary",
                "- Score content quality, SEO readiness, authority, and affiliate fit.",
                "- Establish a minimum quality threshold before new content is published.",
            ],
        ),
        _write_report(
            target_dir,
            "entity-audit.md",
            "Entity Audit",
            [
                "## Summary",
                "- Review entity coverage for organization, software, brand, people, and topic clusters.",
                "- Identify missing entity references that could improve topical authority.",
            ],
        ),
        _write_report(
            target_dir,
            "authority-audit.md",
            "Authority Audit",
            [
                "## Summary",
                "- Review topic coverage, cluster strength, and content gap analysis.",
                "- Measure whether high-value topics have enough supporting authority signals.",
            ],
        ),
        _write_report(
            target_dir,
            "affiliate-audit.md",
            "Affiliate Audit",
            [
                "## Summary",
                "- Review money pages, comparison pages, and CTA placement quality.",
                "- Identify opportunities to improve conversion quality without harming trust.",
            ],
        ),
        _write_report(
            target_dir,
            "performance-audit.md",
            "Performance Audit",
            [
                "## Summary",
                "- Review build speed, publish safety, and deployment readiness.",
                "- Keep the pipeline stable as content volume increases.",
            ],
        ),
        _write_report(
            target_dir,
            "migration-plan.md",
            "Migration Plan",
            [
                "## Summary",
                "- Roll out the new engine behind feature flags.",
                "- Validate each phase with tests and local previews before deployment.",
            ],
        ),
        _write_report(
            target_dir,
            "rollback-plan.md",
            "Rollback Plan",
            [
                "## Summary",
                "- Keep the current workflow intact and reversible.",
                "- Disable new features quickly if validation fails.",
            ],
        ),
    ]

    return reports


if __name__ == "__main__":
    generate_reports()
    print("Generated audit reports")
