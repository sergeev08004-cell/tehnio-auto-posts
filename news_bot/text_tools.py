from __future__ import annotations

import hashlib
import re
import urllib.parse
from typing import List


WORD_RE = re.compile(r"[a-zA-Zа-яА-Я0-9]+")


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    filtered_query = [
        (key, value)
        for key, value in query
        if not key.lower().startswith("utm_")
        and key.lower() not in {"rss", "ref", "source"}
    ]
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        fragment="",
        query=urllib.parse.urlencode(filtered_query)
    )
    return urllib.parse.urlunsplit(normalized)


def tokens_from_text(text: str) -> List[str]:
    return [word.lower() for word in WORD_RE.findall(text)]


def title_key(title: str) -> str:
    return " ".join(tokens_from_text(title))


def fingerprint_from_text(source_name: str, title: str, url: str) -> str:
    payload = f"{source_name}|{title_key(title)}|{normalize_url(url)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
