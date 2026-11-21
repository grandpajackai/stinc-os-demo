"""Checks for text that must not ship on the public STINC OS site.

The site is a public GitHub Pages repo. These checks look for contact
addresses, phone numbers, street addresses, and secret-shaped strings.
They return category names only, never the matched text.
"""
from __future__ import annotations

import re

EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-*]{1,64}@[A-Za-z0-9.\-*]{1,255}\.[A-Za-z]{2,}"
)
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-])?(?:\(?\d{3}\)?[\s.-])\d{3}[\s.-]\d{4}\b"
)
ADDRESS_RE = re.compile(
    r"\b\d{2,6}\s+(?:[A-Za-z0-9.'-]+\s+){0,5}"
    r"(?:Ave|Avenue|St|Street|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Way|Ct|Court)\b",
    re.I,
)
SECRET_RES = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?i)\b(api[_-]?key|secret|password|passwd|access[_-]?token|refresh[_-]?token)\b"
        r"\s*[:=]\s*\S{6,}"
    ),
)
FORBIDDEN_KEYS = {
    "contact_email",
    "contact_name",
    "contact_title",
    "contact_phone",
    "phone",
    "reply_notes",
    "deal_route",
    "deal_type",
    "pay_evidence",
    "margin",
    "margins",
    "api_key",
    "access_token",
    "refresh_token",
    "password",
    "passwd",
    "signature",
    "mailing_address",
    "smtp",
    "brand",
    "brand_key",
}


def find_issues(text: str) -> list[str]:
    """Return category names for anything in text that cannot be published."""
    found: list[str] = []
    if EMAIL_RE.search(text or ""):
        found.append("email")
    if PHONE_RE.search(text or ""):
        found.append("phone")
    if ADDRESS_RE.search(text or ""):
        found.append("address")
    if any(rx.search(text or "") for rx in SECRET_RES):
        found.append("secret")
    return found


def find_key_issues(obj) -> list[str]:
    bad: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).lower() in FORBIDDEN_KEYS:
                    bad.append("forbidden-key")
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(obj)
    return bad
