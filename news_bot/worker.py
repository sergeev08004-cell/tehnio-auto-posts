from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import List

from news_bot.config import AppConfig
from news_bot.feeds import fetch_feed
from news_bot.storage import Storage
from news_bot.text_tools import fingerprint_from_text, normalize_url, title_key, tokens_from_text


NON_NEWS_SCOPE_PATTERNS = (
    re.compile(r"\bnewsletter\b", re.IGNORECASE),
    re.compile(r"\bround-?up\b", re.IGNORECASE),
    re.compile(r"\bweek in review\b", re.IGNORECASE),
    re.compile(r"\bdaily briefing\b", re.IGNORECASE),
    re.compile(r"\bweekly recap\b", re.IGNORECASE),
    re.compile(r"\bwelcome back to\b", re.IGNORECASE),
    re.compile(r"\byour central hub\b", re.IGNORECASE),
    re.compile(r"\beditor'?s note\b", re.IGNORECASE),
    re.compile(r"\bwhy\b.{0,80}\binvested\b", re.IGNORECASE),
    re.compile(r"\bbig bet on\b", re.IGNORECASE),
)
OUT_OF_SCOPE_WORLD_NEWS_PATTERNS = (
    re.compile(r"\bwar\b", re.IGNORECASE),
    re.compile(r"\bmilitary\b", re.IGNORECASE),
    re.compile(r"\bmissile\b", re.IGNORECASE),
    re.compile(r"\bairstrike\b", re.IGNORECASE),
    re.compile(r"\bceasefire\b", re.IGNORECASE),
    re.compile(r"\boccupation\b", re.IGNORECASE),
    re.compile(r"\brefugee\b", re.IGNORECASE),
    re.compile(r"\brefugees\b", re.IGNORECASE),
    re.compile(r"\bdisplaced\b", re.IGNORECASE),
    re.compile(r"\bhumanitarian\b", re.IGNORECASE),
    re.compile(r"\bdiaspora\b", re.IGNORECASE),
    re.compile(r"\brelief\b", re.IGNORECASE),
    re.compile(r"\baid\b", re.IGNORECASE),
    re.compile(r"\battack(?:s)? on\b", re.IGNORECASE),
    re.compile(r"\bisraeli\b", re.IGNORECASE),
    re.compile(r"\blebanon\b", re.IGNORECASE),
    re.compile(r"\bgaza\b", re.IGNORECASE),
    re.compile(r"\bukraine\b", re.IGNORECASE),
    re.compile(r"\biran\b", re.IGNORECASE),
    re.compile(r"\bливан\b", re.IGNORECASE),
    re.compile(r"\bизраил", re.IGNORECASE),
    re.compile(r"\bгаза\b", re.IGNORECASE),
    re.compile(r"\bукраин", re.IGNORECASE),
    re.compile(r"\bиран\b", re.IGNORECASE),
    re.compile(r"\bвойн", re.IGNORECASE),
    re.compile(r"\bбежен", re.IGNORECASE),
    re.compile(r"\bгуманитар", re.IGNORECASE),
    re.compile(r"\bпомощ", re.IGNORECASE),
    re.compile(r"\bперемещен", re.IGNORECASE),
)

@dataclass(frozen=True)
class CollectedItem:
    source_name: str
    source_group: str
    source_language: str
    source_weight: float
    title: str
    title_key: str
    summary: str
    url: str
    image_url: str
    published_at: datetime
    fingerprint: str
    tokens: List[str]
    video_url: str = ""


def collect_candidates(config: AppConfig, storage: Storage, verbose: bool = False) -> List[CollectedItem]:
    collected: List[CollectedItem] = []

    for source in config.sources:
        if not source.enabled:
            continue

        try:
            entries = fetch_feed(source, config)
            if verbose:
                print(f"[fetch] source={source.name} entries={len(entries)}")
        except Exception as error:
            if verbose:
                print(f"[fetch] source={source.name} error={error}")
            continue

        for entry in entries:
            item_title_key = title_key(entry.title)
            fingerprint = fingerprint_from_text(entry.source_name, entry.title, entry.url)
            if storage.was_published(fingerprint) or storage.looks_like_published(item_title_key, normalize_url(entry.url)):
                continue

            lowered_haystack = f"{entry.title} {entry.summary}".lower()
            if any(keyword in lowered_haystack for keyword in config.blocked_keywords):
                continue
            if not source_matches_required_context(entry.source_group, lowered_haystack):
                continue
            if not story_matches_editorial_scope(lowered_haystack):
                continue

            tokens = tokens_from_text(f"{entry.title} {entry.summary}")
            if len(tokens) < 4:
                continue

            collected.append(
                CollectedItem(
                    source_name=entry.source_name,
                    source_group=entry.source_group,
                    source_language=entry.source_language,
                    source_weight=entry.source_weight,
                    title=entry.title,
                    title_key=item_title_key,
                    summary=entry.summary,
                    url=entry.url,
                    image_url=entry.image_url,
                    published_at=entry.published_at,
                    fingerprint=fingerprint,
                    tokens=tokens,
                    video_url=entry.video_url
                )
            )

    return collected


def source_matches_required_context(source_group: str, lowered_haystack: str) -> bool:
    return True


def story_matches_editorial_scope(lowered_haystack: str) -> bool:
    if any(pattern.search(lowered_haystack) for pattern in NON_NEWS_SCOPE_PATTERNS):
        return False
    if any(pattern.search(lowered_haystack) for pattern in OUT_OF_SCOPE_WORLD_NEWS_PATTERNS):
        return False
    return True
