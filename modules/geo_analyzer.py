from __future__ import annotations


def suggest_geos(competition: str, cpc: float) -> dict:
    if competition == "High" or cpc >= 5:
        return {
            "primary_geo": "Canada",
            "secondary_geos": "UK, Australia, Singapore",
            "geo_notes": "US CPC cao; nên test Canada/UK trước rồi mới mở rộng US.",
        }
    if competition == "Medium":
        return {
            "primary_geo": "US",
            "secondary_geos": "Canada, UK, Australia",
            "geo_notes": "Có thể test US với exact/phrase keyword và budget nhỏ.",
        }
    return {
        "primary_geo": "US",
        "secondary_geos": "Canada, UK, Germany, Singapore",
        "geo_notes": "Competition thấp hơn; có thể test nhiều GEO sau khi có CTR ổn.",
    }
