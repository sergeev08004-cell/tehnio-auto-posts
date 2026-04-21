from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List


@dataclass(frozen=True)
class CandidateItem:
    source_name: str
    source_group: str
    source_language: str
    source_weight: float
    source_kind: str
    source_trust: str
    source_in_registry: bool
    title: str
    summary: str
    url: str
    image_url: str
    published_at: datetime
    topic: str
    topic_label: str
    score: float
    duplicate_count: int
    confirmation_count: int
    credibility: str
    post_label: str
    editorial_reason: str
    fingerprint: str
    similar_urls: List[str]
    video_url: str = ""
    original_title: str = ""
    original_summary: str = ""
    persona_name: str = ""
    persona_comment: str = ""
    generated_headline: str = ""
    generated_intro: str = ""
    generated_facts: List[str] = field(default_factory=list)
    generated_hashtags: List[str] = field(default_factory=list)

    @property
    def published_at_utc(self) -> datetime:
        if self.published_at.tzinfo is None:
            return self.published_at.replace(tzinfo=timezone.utc)
        return self.published_at.astimezone(timezone.utc)
