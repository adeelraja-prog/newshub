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


def priority_band(story, trusted_publisher=False):
    """P1-P4 editorial desk classification. P5 is assigned to duplicate/stale intake rejects."""
    if story.get("stale"):
        return "P5"
    review = story.get("quality_review") or {}
    source = story.get("original_source") or {}
    source_unclear = (not trusted_publisher and
                      (str(source.get("type", "unknown")).lower() == "unknown" or
                       not source.get("url")))
    if (review.get("decision") == "research_required" or
        str(story.get("claim_status", "")).lower() == "unverified" or source_unclear):
        return "P4"
    confidence = int(story.get("confidence", 0) or 0)
    urgency = int(story.get("urgency", 0) or 0)
    if urgency >= 85 and confidence >= 75:
        return "P1"
    importance = int(story.get("importance", 0) or 0)
    public_interest = int(story.get("public_interest", 0) or 0)
    national = int(story.get("national_impact", 0) or 0)
    regional = int(story.get("regional_impact", 0) or 0)
    global_ = int(story.get("global_impact", 0) or 0)
    if importance >= 70 or public_interest >= 80 or national >= 70 or regional >= 75 or global_ >= 80:
        return "P2"
    return "P3"
