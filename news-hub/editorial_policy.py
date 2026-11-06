"""Adeel Raja News Hub editorial scope policy (deterministic final gate)."""
ALLOWED_SCOPES = {"national", "international"}
MIN_CONFIDENCE = 75
MIN_IMPORTANCE = 75
MIN_PUBLIC_INTEREST = 65
MIN_NATIONAL_IMPACT = 70
MIN_GLOBAL_IMPACT = 80

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
    if scope == "national" and int(story.get("national_impact", 0) or 0) < MIN_NATIONAL_IMPACT:
        return False, "not enough national impact"
    if scope == "international" and int(story.get("global_impact", 0) or 0) < MIN_GLOBAL_IMPACT:
        if int(story.get("pakistan_relevance", 0) or 0) < 75 or not story.get("why_pk"):
            return False, "neither globally major nor strongly relevant to Pakistan"
    return True, "eligible"
