from __future__ import annotations


def generate_angles(brand_name: str, niche: str) -> dict:
    label = niche or "software"
    return {
        "pain_angle": f"Reduce manual work in {label} workflows.",
        "fear_angle": f"Avoid falling behind teams already using {label} automation.",
        "productivity_angle": f"Save hours each week with a focused {label} stack.",
        "beginner_angle": f"Start with {brand_name} without a complex setup.",
        "roi_angle": f"Test whether {brand_name} can pay back from one extra customer.",
        "speed_angle": f"Launch a usable {label} workflow faster.",
        "automation_angle": f"Automate repeated tasks before scaling campaigns.",
        "enterprise_angle": f"Give teams a clearer, more repeatable {label} process.",
    }
