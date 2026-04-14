from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceConfig:
    name: str
    url: str
    language: str
    weight: float
    group: str
    enabled: bool = True


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    channel_id: str
    parse_mode: str = "HTML"
    disable_web_page_preview: bool = False


@dataclass(frozen=True)
class TranslationConfig:
    enabled: bool
    provider: str
    target_language: str
    source_languages: List[str]


@dataclass(frozen=True)
class DiversityConfig:
    enabled: bool
    max_per_publisher: int
    max_per_topic: int
    topic_repeat_penalty: float
    publisher_repeat_penalty: float
    topic_limits: Dict[str, int]


@dataclass(frozen=True)
class EditorialConfig:
    profile: str
    insider_label: str
    news_label: str
    link_text: str
    persona_comments_enabled: bool
    subscribe_cta_text: str


@dataclass(frozen=True)
class LlmConfig:
    enabled: bool
    provider: str
    model: str
    api_key: str
    base_url: str
    temperature: float
    summary_max_sentences: int
    persona_max_chars: int


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramConfig
    poll_interval_minutes: int
    max_posts_per_cycle: int
    min_post_age_minutes: int
    max_post_age_hours: int
    min_publish_gap_minutes: int
    request_timeout_seconds: int
    database_path: str
    user_agent: str
    publication_title: str
    sources: List[SourceConfig]
    allowed_topics: List[str]
    priority_topics: List[str]
    blocked_keywords: List[str]
    translation: TranslationConfig
    diversity: DiversityConfig
    editorial: EditorialConfig
    llm: LlmConfig


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}. Copy config.example.json to config.json first."
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    telegram_payload = payload["telegram"]
    bot_token = resolve_secret(telegram_payload, "bot_token")
    telegram = TelegramConfig(
        bot_token=bot_token,
        channel_id=telegram_payload["channel_id"],
        parse_mode=str(telegram_payload.get("parse_mode", "HTML") or "HTML"),
        disable_web_page_preview=bool(telegram_payload.get("disable_web_page_preview", False))
    )
    translation_payload = payload.get("translation", {})
    translation = TranslationConfig(
        enabled=bool(translation_payload.get("enabled", False)),
        provider=str(translation_payload.get("provider", "google_web")),
        target_language=str(translation_payload.get("target_language", "ru")),
        source_languages=[str(item).lower() for item in translation_payload.get("source_languages", ["en"])]
    )
    diversity_payload = payload.get("diversity", {})
    diversity = DiversityConfig(
        enabled=bool(diversity_payload.get("enabled", True)),
        max_per_publisher=max(1, int(diversity_payload.get("max_per_publisher", 1))),
        max_per_topic=max(1, int(diversity_payload.get("max_per_topic", 2))),
        topic_repeat_penalty=float(diversity_payload.get("topic_repeat_penalty", 1.15)),
        publisher_repeat_penalty=float(diversity_payload.get("publisher_repeat_penalty", 0.85)),
        topic_limits={
            str(topic).lower(): max(1, int(limit))
            for topic, limit in diversity_payload.get("topic_limits", {"recalls": 1}).items()
        }
    )
    editorial_payload = payload.get("editorial", {})
    editorial = EditorialConfig(
        profile=str(editorial_payload.get("profile", "default") or "default"),
        insider_label=str(editorial_payload.get("insider_label", "🕵️‍♂️ ИНСАЙД") or "🕵️‍♂️ ИНСАЙД"),
        news_label=str(editorial_payload.get("news_label", "✅ НОВОСТЬ") or "✅ НОВОСТЬ"),
        link_text=str(editorial_payload.get("link_text", "Подробности ниже 👇") or "Подробности ниже 👇"),
        persona_comments_enabled=bool(editorial_payload.get("persona_comments_enabled", False)),
        subscribe_cta_text=str(editorial_payload.get("subscribe_cta_text", "") or "").strip()
    )
    llm_payload = payload.get("llm", {})
    llm = LlmConfig(
        enabled=bool(llm_payload.get("enabled", False)),
        provider=str(llm_payload.get("provider", "openai") or "openai").lower(),
        model=str(llm_payload.get("model", "gpt-4o-mini") or "gpt-4o-mini"),
        api_key=resolve_secret(llm_payload, "api_key"),
        base_url=str(llm_payload.get("base_url", "") or "").strip(),
        temperature=float(llm_payload.get("temperature", 0.6)),
        summary_max_sentences=max(2, int(llm_payload.get("summary_max_sentences", 4))),
        persona_max_chars=max(90, int(llm_payload.get("persona_max_chars", 180)))
    )

    sources = [
        SourceConfig(
            name=source["name"],
            url=source["url"],
            language=source.get("language", "ru"),
            weight=float(source.get("weight", 1.0)),
            group=derive_source_group(source),
            enabled=bool(source.get("enabled", True))
        )
        for source in payload.get("sources", [])
    ]

    if not telegram.bot_token or "PASTE_TELEGRAM_BOT_TOKEN_HERE" in telegram.bot_token:
        raise ValueError("Fill telegram.bot_token in config.json")

    if not telegram.channel_id:
        raise ValueError("Fill telegram.channel_id in config.json")

    if not sources:
        raise ValueError("Add at least one enabled source to config.json")

    return AppConfig(
        telegram=telegram,
        poll_interval_minutes=int(payload.get("poll_interval_minutes", 30)),
        max_posts_per_cycle=int(payload.get("max_posts_per_cycle", 3)),
        min_post_age_minutes=int(payload.get("min_post_age_minutes", 5)),
        max_post_age_hours=int(payload.get("max_post_age_hours", 24)),
        min_publish_gap_minutes=int(payload.get("min_publish_gap_minutes", 20)),
        request_timeout_seconds=int(payload.get("request_timeout_seconds", 20)),
        database_path=str(payload.get("database_path", "data/news.db")),
        user_agent=str(payload.get("user_agent", "AutoNewsBot/1.0")),
        publication_title=str(payload.get("publication_title", "")),
        sources=sources,
        allowed_topics=[str(item).lower() for item in payload.get("allowed_topics", [])],
        priority_topics=list(payload.get("priority_topics", [])),
        blocked_keywords=[item.lower() for item in payload.get("blocked_keywords", [])],
        translation=translation,
        diversity=diversity,
        editorial=editorial,
        llm=llm
    )


def derive_source_group(source: dict) -> str:
    explicit_group = str(source.get("group", "")).strip().lower()
    if explicit_group:
        return explicit_group

    host = urlparse(str(source.get("url", ""))).hostname or ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    if host:
        parts = [part for part in host.split(".") if part]
        if len(parts) >= 2:
            return parts[-2]
        return parts[0]

    name = str(source.get("name", "")).strip().lower()
    normalized = re.sub(r"[^0-9a-zа-я]+", "-", name).strip("-")
    return normalized or "source"


def resolve_secret(payload: dict, key: str) -> str:
    direct_value = str(payload.get(key, "") or "").strip()
    if direct_value:
        return direct_value

    env_name = str(payload.get(f"{key}_env", "") or "").strip()
    if env_name:
        return os.getenv(env_name, "").strip()

    return ""
