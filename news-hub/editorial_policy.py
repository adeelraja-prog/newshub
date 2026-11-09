"""Adeel Raja News Hub editorial scope policy (deterministic final gate)."""
ALLOWED_SCOPES = {"national", "provincial", "international"}
MIN_CONFIDENCE = 80
MIN_IMPORTANCE = 82
MIN_PUBLIC_INTEREST = 75
MIN_URGENCY = 65
MIN_NATIONAL_IMPACT = 75
MIN_REGIONAL_IMPACT = 85
MIN_GLOBAL_IMPACT = 85

def eligible(story):
    scope = str(story.get("scope", "")).lower()
    if scope not in ALLOWED_SCOPES:
        return False, "regional/local/unknown scope"
    if str(story.get("importance_class", "")).lower() != "major":
        return False, "not classified as a major event"
    if int(story.get("confidence", 0) or 0) < MIN_CONFIDENCE:
        return False, "insufficient source confidence"
    if int(story.get("importance", 0) or 0) < MIN_IMPORTANCE:
        return False, "insufficient public importance"
    if int(story.get("public_interest", 0) or 0) < MIN_PUBLIC_INTEREST:
        return False, "insufficient public interest"
    if int(story.get("urgency", 0) or 0) < MIN_URGENCY:
        return False, "not a sufficiently urgent current headline"
    if scope == "national" and int(story.get("national_impact", 0) or 0) < MIN_NATIONAL_IMPACT:
        return False, "not enough national impact"
    if scope == "provincial" and int(story.get("regional_impact", 0) or 0) < MIN_REGIONAL_IMPACT:
        return False, "not enough province-wide public impact"
    if scope == "international" and int(story.get("global_impact", 0) or 0) < MIN_GLOBAL_IMPACT:
        if int(story.get("pakistan_relevance", 0) or 0) < 80 or not story.get("why_pk"):
            return False, "neither globally major nor strongly relevant to Pakistan"
    return True, "eligible"
