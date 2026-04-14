from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable
from urllib.parse import urlsplit

from news_bot.text_tools import tokens_from_text

if TYPE_CHECKING:
    from news_bot.worker import CollectedItem


@dataclass(frozen=True)
class SourceProfile:
    name: str
    kind: str
    trust: str
    in_registry: bool
    aliases: tuple[str, ...]
    specialties: tuple[str, ...] = ()


@dataclass(frozen=True)
class EditorialAssessment:
    source_kind: str
    source_trust: str
    source_in_registry: bool
    credibility: str
    post_label: str
    should_publish: bool
    impact_score: int
    confirmation_count: int
    reason: str


LOW_VALUE_MARKERS = (
    "newsletter",
    "roundup",
    "round-up",
    "podcast",
    "opinion",
    "editorial",
    "best ",
    "best-",
    "guide",
    "gift guide",
    "buying guide",
    "how to",
    "hands-on",
    "review",
    "reviews",
    "accessory",
    "accessories",
    "watch bands",
    "this weekend",
    "watch now",
    "/video",
    " video",
)
OUT_OF_SCOPE_NEWS_MARKERS = (
    "war",
    "military",
    "missile",
    "airstrike",
    "ceasefire",
    "occupation",
    "refugee",
    "refugees",
    "displaced",
    "humanitarian",
    "diaspora",
    "relief",
    " aid ",
    "israeli",
    "lebanon",
    "gaza",
    "ukraine",
    "iran",
    "войн",
    "гуманитар",
    "бежен",
    "перемещен",
    "израил",
    "ливан",
    "газа",
    "украин",
    "иран",
)
RUMOR_MARKERS = (
    "rumor",
    "rumours",
    "rumored",
    "leak",
    "leaks",
    "leaked",
    "reportedly",
    "expected to",
    "could",
    "may",
    "might",
    "tipster",
    "слух",
    "слухи",
    "инсайд",
    "утечк",
    "ожидает",
    "ожидается",
)
CONTRADICTION_MARKERS = (
    "fake",
    "false",
    "debunked",
    "not happening",
    "denied",
    "опроверг",
    "фейк",
    "ложн",
)
IMPACT_MARKERS = (
    "launch",
    "launches",
    "launched",
    "release",
    "released",
    "unveil",
    "unveils",
    "announced",
    "announce",
    "pricing",
    "price",
    "subscription",
    "update",
    "rollout",
    "security",
    "privacy",
    "ban",
    "chip",
    "chips",
    "processor",
    "ai",
    "robot",
    "robotics",
    "assistant",
    "gpu",
    "cpu",
    "смартфон",
    "ноутбук",
    "чип",
    "процессор",
    "безопасност",
    "обновлен",
    "релиз",
    "запуск",
    "представ",
    "выпуст",
)
USER_IMPACT_MARKERS = (
    "users",
    "customers",
    "developers",
    "buyers",
    "enterprise",
    "consumer",
    "availability",
    "customers",
    "пользоват",
    "клиент",
    "разработч",
    "подписк",
)
TREND_MARKERS = (
    "apple",
    "iphone",
    "ipad",
    "mac",
    "vision pro",
    "samsung",
    "galaxy",
    "google",
    "pixel",
    "openai",
    "microsoft",
    "copilot",
    "nvidia",
    "amd",
    "intel",
    "qualcomm",
    "tesla",
    "ai",
    "robot",
    "robotics",
    "chip",
    "gpu",
    "assistant",
    "android",
    "wearable",
    "display",
    "smartphone",
    "laptop",
    "apple",
    "смартфон",
    "ноутбук",
    "робот",
    "ии",
    "диспле",
)
ACTION_MARKERS = (
    "launch",
    "launches",
    "launched",
    "announced",
    "announces",
    "released",
    "revealed",
    "reveals",
    "rolled out",
    "prices",
    "expands",
    "partners",
    "представ",
    "выпуст",
    "запуст",
    "показал",
    "объявил",
    "добавил",
)
NEWS_SIGNAL_MARKERS = (
    "policy",
    "copyright",
    "security",
    "privacy",
    "pricing",
    "subscription",
    "ban",
    "lawsuit",
    "launch",
    "release",
    "rollout",
    "update",
    "partnership",
    "acquisition",
    "merger",
    "policy",
    "правил",
    "цена",
    "подписк",
    "обновлен",
    "политик",
    "запуск",
    "релиз",
)


SOURCE_PROFILES = (
    SourceProfile(
        name="The Verge",
        kind="media",
        trust="high",
        in_registry=True,
        aliases=("the verge", "theverge", "www the verge com", "thevergecom"),
    ),
    SourceProfile(
        name="Bloomberg",
        kind="media",
        trust="high",
        in_registry=True,
        aliases=("bloomberg", "bloomberg tech", "bloombergcom", "feeds bloomberg com"),
    ),
    SourceProfile(
        name="Reuters",
        kind="media",
        trust="high",
        in_registry=True,
        aliases=("reuters", "reuters tech", "reuterscom"),
    ),
    SourceProfile(
        name="CNBC Tech",
        kind="media",
        trust="high",
        in_registry=True,
        aliases=("cnbc", "cnbc tech", "tech", "cnbccom"),
    ),
    SourceProfile(
        name="TechCrunch",
        kind="media",
        trust="high",
        in_registry=True,
        aliases=("techcrunch", "tech crunch", "techcrunchcom"),
    ),
    SourceProfile(
        name="Engadget",
        kind="media",
        trust="high",
        in_registry=True,
        aliases=("engadget", "engadgetcom"),
    ),
    SourceProfile(
        name="MIT Technology Review",
        kind="media",
        trust="high",
        in_registry=True,
        aliases=("mit technology review", "technology review", "technologyreview", "technologyreviewcom"),
    ),
    SourceProfile(
        name="9to5Mac",
        kind="media",
        trust="high",
        in_registry=True,
        aliases=("9to5mac", "9to5 mac", "9to5maccom"),
    ),
    SourceProfile(
        name="MacRumors",
        kind="media",
        trust="high",
        in_registry=True,
        aliases=("macrumors", "mac rumors", "macrumorscom"),
    ),
    SourceProfile(
        name="WIRED",
        kind="media",
        trust="high",
        in_registry=True,
        aliases=("wired", "wiredcom"),
    ),
    SourceProfile(
        name="Ars Technica",
        kind="media",
        trust="high",
        in_registry=True,
        aliases=("ars technica", "arstechnica", "arstechnicacom"),
    ),
    SourceProfile(
        name="Ming-Chi Kuo",
        kind="insider",
        trust="high",
        in_registry=True,
        aliases=("ming-chi kuo", "ming chi kuo", "kuo"),
        specialties=("apple", "iphone", "ipad", "mac", "vision pro", "airpods"),
    ),
    SourceProfile(
        name="Mark Gurman",
        kind="insider",
        trust="high",
        in_registry=True,
        aliases=("mark gurman", "gurman", "power on"),
        specialties=("apple", "iphone", "ipad", "mac", "watch", "airpods"),
    ),
    SourceProfile(
        name="Ross Young",
        kind="insider",
        trust="high",
        in_registry=True,
        aliases=("ross young",),
        specialties=("display", "screen", "oled", "foldable", "диспле", "экран"),
    ),
    SourceProfile(
        name="Jeff Pu",
        kind="insider",
        trust="high",
        in_registry=True,
        aliases=("jeff pu",),
        specialties=("apple", "iphone", "ipad", "mac", "display"),
    ),
    SourceProfile(
        name="Ice Universe",
        kind="insider",
        trust="medium",
        in_registry=True,
        aliases=("ice universe",),
        specialties=("samsung", "galaxy", "display", "foldable"),
    ),
    SourceProfile(
        name="Digital Chat Station",
        kind="insider",
        trust="medium",
        in_registry=True,
        aliases=("digital chat station",),
        specialties=("xiaomi", "honor", "oppo", "vivo", "oneplus", "china", "китай"),
    ),
    SourceProfile(
        name="LeaksApplePro",
        kind="insider",
        trust="medium",
        in_registry=True,
        aliases=("leaksapplepro", "leaks apple pro"),
        specialties=("apple", "iphone", "ipad", "mac", "ios", "watch"),
    ),
    SourceProfile(
        name="OnLeaks",
        kind="insider",
        trust="medium",
        in_registry=True,
        aliases=("onleaks",),
        specialties=("render", "design", "cad", "смартфон", "device"),
    ),
    SourceProfile(
        name="ShrimpApplePro",
        kind="insider",
        trust="medium",
        in_registry=True,
        aliases=("shrimpapplepro",),
        specialties=("apple", "iphone", "ipad", "mac"),
    ),
    SourceProfile(
        name="yeux1122",
        kind="insider",
        trust="medium",
        in_registry=True,
        aliases=("yeux1122",),
        specialties=("apple", "samsung", "display"),
    ),
    SourceProfile(
        name="Apple Newsroom",
        kind="official",
        trust="medium",
        in_registry=False,
        aliases=("apple newsroom", "apple", "applecom"),
        specialties=("apple", "iphone", "ipad", "mac", "airpods", "watch"),
    ),
    SourceProfile(
        name="Google Blog",
        kind="official",
        trust="medium",
        in_registry=False,
        aliases=("google blog", "google", "blog google", "googlecom"),
        specialties=("google", "android", "pixel", "gemini", "wear os"),
    ),
    SourceProfile(
        name="Samsung Newsroom",
        kind="official",
        trust="medium",
        in_registry=False,
        aliases=("samsung newsroom", "samsung", "samsungcom"),
        specialties=("samsung", "galaxy", "display", "foldable"),
    ),
    SourceProfile(
        name="OpenAI News",
        kind="official",
        trust="medium",
        in_registry=False,
        aliases=("openai news", "openai blog", "openai", "openaicom"),
        specialties=("openai", "chatgpt", "gpt", "ai", "assistant"),
    ),
)
UNKNOWN_SOURCE_PROFILE = SourceProfile(
    name="Unknown",
    kind="unknown",
    trust="low",
    in_registry=False,
    aliases=(),
)


def assess_story(primary: "CollectedItem", group: Iterable["CollectedItem"], topic: str) -> EditorialAssessment:
    group_items = list(group)
    profile = classify_source(primary.source_name, primary.source_group, primary.url)
    story_text = f"{primary.title} {primary.summary}".lower()
    text = f"{story_text} {primary.url}".lower()
    impact_score = calculate_impact_score(story_text, topic)
    confirmation_count = count_confirmations(group_items)
    rumor_story = profile.kind == "insider" or contains_any(story_text, RUMOR_MARKERS)
    trend_alignment = matches_market_trend(story_text, topic)
    plausible = is_plausible_story(story_text, topic, profile)
    contradiction = contains_any(story_text, CONTRADICTION_MARKERS)
    low_value = contains_any(text, LOW_VALUE_MARKERS)
    out_of_scope = contains_any(story_text, OUT_OF_SCOPE_NEWS_MARKERS)
    news_signal = contains_any(story_text, ACTION_MARKERS) or contains_any(story_text, NEWS_SIGNAL_MARKERS) or confirmation_count >= 2
    has_value = impact_score >= 2 and not low_value and (news_signal or (rumor_story and impact_score >= 3))

    credibility = determine_credibility(
        profile=profile,
        rumor_story=rumor_story,
        confirmation_count=confirmation_count,
        trend_alignment=trend_alignment,
        plausible=plausible,
        contradiction=contradiction or out_of_scope,
        impact_score=impact_score,
    )
    should_publish = should_publish_story(
        profile=profile,
        credibility=credibility,
        impact_score=impact_score,
        confirmation_count=confirmation_count,
        has_value=has_value and not out_of_scope,
        rumor_story=rumor_story,
        plausible=plausible and not out_of_scope,
    )
    post_label = credibility_to_post_label(credibility, profile.kind, rumor_story)
    reason = build_reason(profile, credibility, confirmation_count, impact_score, rumor_story, trend_alignment)

    return EditorialAssessment(
        source_kind=profile.kind,
        source_trust=profile.trust,
        source_in_registry=profile.in_registry,
        credibility=credibility,
        post_label=post_label,
        should_publish=should_publish,
        impact_score=impact_score,
        confirmation_count=confirmation_count,
        reason=reason,
    )


def classify_source(source_name: str, source_group: str, url: str) -> SourceProfile:
    candidates = source_identity_candidates(source_name, source_group, url)
    for profile in SOURCE_PROFILES:
        if any(alias in candidate or candidate in alias for alias in profile.aliases for candidate in candidates if candidate):
            return profile
    return UNKNOWN_SOURCE_PROFILE


def source_identity_candidates(source_name: str, source_group: str, url: str) -> tuple[str, ...]:
    host = urlsplit(url).netloc.lower().lstrip("www.")
    host_core = host.replace(".", " ")
    return (
        normalize_key(source_name),
        normalize_key(source_group),
        normalize_key(host),
        normalize_key(host_core),
    )


def normalize_key(value: str) -> str:
    return re.sub(r"[^0-9a-zа-я]+", " ", (value or "").lower()).strip()


def count_confirmations(group_items: list["CollectedItem"]) -> int:
    groups = {
        normalize_key(item.source_group or item.source_name)
        for item in group_items
        if normalize_key(item.source_group or item.source_name)
    }
    return len(groups)


def determine_credibility(
    profile: SourceProfile,
    rumor_story: bool,
    confirmation_count: int,
    trend_alignment: bool,
    plausible: bool,
    contradiction: bool,
    impact_score: int,
) -> str:
    if contradiction or not plausible:
        return "low"

    if rumor_story:
        if profile.trust == "high" and (confirmation_count >= 2 or trend_alignment) and impact_score >= 2:
            return "medium"
        if profile.trust == "medium" and confirmation_count >= 2 and impact_score >= 2:
            return "medium"
        return "low"

    if profile.kind == "media":
        if profile.trust == "high" and confirmation_count >= 2 and impact_score >= 2:
            return "high"
        if profile.trust == "high" and impact_score >= 3 and trend_alignment:
            return "high"
        if profile.trust in {"high", "medium"} and impact_score >= 2:
            return "medium"
        return "low"

    if profile.kind == "official":
        if impact_score >= 3:
            return "high"
        return "medium"

    if profile.trust == "high" and confirmation_count >= 2 and impact_score >= 2:
        return "high"
    if profile.trust in {"high", "medium"} and confirmation_count >= 2 and impact_score >= 2:
        return "medium"
    return "low"


def should_publish_story(
    profile: SourceProfile,
    credibility: str,
    impact_score: int,
    confirmation_count: int,
    has_value: bool,
    rumor_story: bool,
    plausible: bool,
) -> bool:
    if not has_value or not plausible:
        return False

    if credibility == "high":
        return True

    if credibility == "medium":
        return profile.kind in {"insider", "media", "official"}

    strong_rumor = rumor_story and profile.kind == "insider" and profile.trust in {"high", "medium"} and impact_score >= 3
    return strong_rumor and confirmation_count >= 2


def credibility_to_post_label(credibility: str, source_kind: str, rumor_story: bool) -> str:
    if source_kind == "insider" or rumor_story:
        return "🕵️‍♂️ ИНСАЙД"
    if credibility in {"high", "medium"} and source_kind in {"media", "official"}:
        return "✅ НОВОСТЬ"
    if credibility == "high":
        return "✅ НОВОСТЬ"
    return ""


def build_reason(
    profile: SourceProfile,
    credibility: str,
    confirmation_count: int,
    impact_score: int,
    rumor_story: bool,
    trend_alignment: bool,
) -> str:
    parts = [profile.kind, profile.trust, credibility]
    if confirmation_count >= 2:
        parts.append("confirmed")
    if rumor_story:
        parts.append("rumor")
    if trend_alignment:
        parts.append("trend-fit")
    if impact_score >= 3:
        parts.append("high-impact")
    return ",".join(parts)


def calculate_impact_score(text: str, topic: str) -> int:
    score = 0
    if contains_any(text, IMPACT_MARKERS):
        score += 1
    if contains_any(text, USER_IMPACT_MARKERS):
        score += 1
    if contains_any(text, TREND_MARKERS):
        score += 1
    if contains_any(text, ACTION_MARKERS):
        score += 1
    if any(character.isdigit() for character in text):
        score += 1
    if topic in {"gadgets", "technology", "new_models", "prices"}:
        score += 1
    return score


def matches_market_trend(text: str, topic: str) -> bool:
    if topic in {"gadgets", "technology", "new_models", "prices"}:
        return True
    return contains_any(text, TREND_MARKERS)


def is_plausible_story(text: str, topic: str, profile: SourceProfile) -> bool:
    tokens = tokens_from_text(text)
    if len(tokens) < 8:
        return False
    if contains_any(text, CONTRADICTION_MARKERS):
        return False
    if profile.specialties and profile.kind == "insider":
        return contains_any(text, profile.specialties)
    if profile.kind == "unknown" and topic not in {"gadgets", "technology", "new_models"}:
        return False
    return True


def contains_any(text: str, markers: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)
