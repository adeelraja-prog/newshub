"""Controversy desk: evidence-led archive of public statements and changing positions.

This module deliberately stores attributed, source-backed statements only. It does not invent
quotes, infer a contradiction from a headline, or auto-publish a comparison. Editorial review
is required before a historical-position comparison is published.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SCHEMA_VERSION = 1
DEFAULT_PATH = Path(os.getenv("CONTROVERSY_LEDGER", "bot-data/controversy-ledger.json"))
VALID_KINDS = {"direct_quote", "official_statement", "interview", "parliamentary_record",
               "court_record", "social_post", "reported_position"}
VALID_STANCES = {"support", "oppose", "conditional", "unclear"}
MAX_QUOTE_CHARS = 420


def _text(value, limit=1000):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _url_ok(value):
    try:
        p = urlparse(str(value or ""))
        return p.scheme == "https" and bool(p.netloc)
    except Exception:
        return False


def issue_key(topic, actor):
    raw = (_text(actor, 120).casefold() + "|" + _text(topic, 220).casefold())
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def statement_id(record):
    raw = "|".join((_text(record.get("person"), 120).casefold(),
                    _text(record.get("topic"), 220).casefold(),
                    _text(record.get("date"), 40),
                    _text(record.get("source_url"), 500)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def empty_ledger():
    return {"schema_version": SCHEMA_VERSION, "updated_at": None, "statements": []}


def load_ledger(path=DEFAULT_PATH):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("schema_version") == SCHEMA_VERSION and isinstance(data.get("statements"), list):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return empty_ledger()


def save_ledger(data, path=DEFAULT_PATH):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


def validate_statement(raw):
    """Return a clean record or (None, reason). Never accept unsourced quote text."""
    if not isinstance(raw, dict):
        return None, "record is not an object"
    person = _text(raw.get("person"), 120)
    topic = _text(raw.get("topic"), 220)
    position = _text(raw.get("position"), 500)
    quote = _text(raw.get("quote"), MAX_QUOTE_CHARS)
    source_url = _text(raw.get("source_url"), 1000)
    source_name = _text(raw.get("source_name"), 120)
    date = _text(raw.get("date"), 40)
    kind = _text(raw.get("kind"), 40)
    stance = _text(raw.get("stance"), 20)
    if not all((person, topic, position, source_name, date)):
        return None, "missing person, topic, position, source name or date"
    if not _url_ok(source_url):
        return None, "source URL must be HTTPS"
    if kind not in VALID_KINDS:
        return None, "unsupported statement type"
    if stance not in VALID_STANCES:
        return None, "unsupported stance label"
    if quote and not raw.get("quote_verified"):
        return None, "verbatim quote has not been verified against the linked source"
    try:
        datetime.fromisoformat(date.replace("Z", "+00:00"))
    except ValueError:
        return None, "date must be ISO-8601 with a year"
    clean = {
        "person": person, "topic": topic, "position": position, "quote": quote,
        "quote_verified": bool(raw.get("quote_verified")), "date": date,
        "source_name": source_name, "source_url": source_url, "kind": kind,
        "stance": stance, "confidence": max(0, min(100, int(raw.get("confidence", 0)))),
        "source_excerpt": _text(raw.get("source_excerpt"), 1200),
        "review_status": "needs_editor_review",
    }
    clean["id"] = statement_id(clean)
    clean["issue_key"] = issue_key(topic, person)
    return clean, None


def add_statements(ledger, candidates):
    """Append new source-backed records; duplicates are ignored."""
    known = {x.get("id") for x in ledger.get("statements", [])}
    added, rejected = [], []
    for raw in candidates if isinstance(candidates, list) else []:
        record, error = validate_statement(raw)
        if error:
            rejected.append({"reason": error, "person": _text((raw or {}).get("person"), 120)})
            continue
        if record["id"] in known:
            continue
        ledger.setdefault("statements", []).append(record)
        known.add(record["id"])
        added.append(record["id"])
    return added, rejected


def candidate_comparisons(ledger, min_confidence=70):
    """Find same-person/same-issue records with materially different stance labels.

    This is a lead for an editor, not proof of hypocrisy or a publishable contradiction.
    """
    groups = {}
    for rec in ledger.get("statements", []):
        if rec.get("confidence", 0) < min_confidence:
            continue
        if rec.get("review_status") == "rejected":
            continue
        groups.setdefault(rec.get("issue_key"), []).append(rec)
    out = []
    for key, rows in groups.items():
        rows.sort(key=lambda x: x.get("date", ""))
        if len(rows) < 2:
            continue
        for i, older in enumerate(rows[:-1]):
            for newer in rows[i + 1:]:
                if older.get("stance") == "unclear" or newer.get("stance") == "unclear":
                    continue
                if older.get("stance") == newer.get("stance"):
                    continue
                if older.get("person", "").casefold() != newer.get("person", "").casefold():
                    continue
                out.append({
                    "issue_key": key, "person": newer["person"], "topic": newer["topic"],
                    "older_statement_id": older["id"], "newer_statement_id": newer["id"],
                    "older_date": older["date"], "newer_date": newer["date"],
                    "older_source": older["source_name"], "newer_source": newer["source_name"],
                    "editorial_status": "needs_human_comparison",
                    "warning": "Different stance labels are a research lead, not proof of contradiction. "
                               "Check context, wording, dates and whether circumstances changed."
                })
    return out
