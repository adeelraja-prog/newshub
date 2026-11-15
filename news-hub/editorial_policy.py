"""Adeel Raja News Hub editorial scope policy (deterministic final gate).

A two-lane gate keeps verification strict while allowing consequential public-interest
stories that were previously lost to overly narrow numeric cut-offs. Thresholds do not
override sourcing, attribution, freshness, language or fact-check requirements.
"""
ALLOWED_SCOPES = {"national", "provincial", "international"}
MIN_CONFIDENCE = 60
MIN_IMPORTANCE = 55
MIN_PUBLIC_INTEREST = 50
MIN_URGENCY = 35
MIN_NATIONAL_IMPACT = 45
MIN_REGIONAL_IMPACT = 60
MIN_GLOBAL_IMPACT = 60


def eligible(story):
    scope = str(story.get("scope", "")).lower()
    if scope not in ALLOWED_SCOPES:
        return False, "regional/local/unknown scope"
    sensitive = str(story.get("category", "")).lower() in {"politics", "courts", "security", "crime", "war", "us_politics"}
    confidence_floor = 70 if sensitive else MIN_CONFIDENCE
    if int(story.get("confidence", 0) or 0) < confidence_floor:
        return False, "insufficient source confidence"
    if int(story.get("importance", 0) or 0) < MIN_IMPORTANCE:
        return False, "insufficient public importance"
    if int(story.get("public_interest", 0) or 0) < MIN_PUBLIC_INTEREST:
        return False, "insufficient public interest"
    if int(story.get("urgency", 0) or 0) < MIN_URGENCY:
        return False, "not a sufficiently current headline"
    if scope == "national" and int(story.get("national_impact", 0) or 0) < MIN_NATIONAL_IMPACT:
        return False, "not enough national impact"
    if scope == "provincial" and int(story.get("regional_impact", 0) or 0) < MIN_REGIONAL_IMPACT:
        return False, "not enough province-wide public impact"
    if scope == "international" and int(story.get("global_impact", 0) or 0) < MIN_GLOBAL_IMPACT:
        if int(story.get("pakistan_relevance", 0) or 0) < 70 or not story.get("why_pk"):
            return False, "neither globally significant nor strongly relevant to Pakistan"
    return True, "eligible"
