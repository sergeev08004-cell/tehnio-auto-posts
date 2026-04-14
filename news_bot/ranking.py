from __future__ import annotations

from collections import Counter
import math
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, List, Tuple

from news_bot.config import DiversityConfig
from news_bot.editorial import assess_story
from news_bot.models import CandidateItem
from news_bot.storage import Storage
from news_bot.text_tools import normalize_url

if TYPE_CHECKING:
    from news_bot.worker import CollectedItem


TOPIC_RULES = {
    "accidents": {
        "label": "ДТП и аварии",
        "weight": 3.15,
        "keywords": [
            "дтп",
            "авари",
            "столкнов",
            "наезд",
            "перевернул",
            "crash",
            "collision",
            "pileup",
            "pile-up",
            "wreck",
            "road accident",
            "traffic accident",
            "fatal crash",
            "highway incident"
        ]
    },
    "recalls": {
        "label": "Отзывная кампания",
        "weight": 2.6,
        "keywords": ["отзыв", "recall", "service action", "дефект", "неисправн", "кампания"]
    },
    "law": {
        "label": "Регулирование",
        "weight": 3.5,
        "keywords": ["закон", "штраф", "пдд", "осаго", "налог", "регулятор", "government", "rule"]
    },
    "new_models": {
        "label": "Новая модель",
        "weight": 3.2,
        "keywords": ["представ", "дебют", "новый", "launch", "debut", "unveil", "reveals", "arrives"]
    },
    "prices": {
        "label": "Цены",
        "weight": 2.8,
        "keywords": ["цены", "ценой", "цену", "стоимост", "price", "pricing", "costs", "$", "usd", "eur", "руб"]
    },
    "sales": {
        "label": "Продажи",
        "weight": 2.7,
        "keywords": ["продаж", "sales", "рынок", "market", "спрос", "dealer"]
    },
    "production": {
        "label": "Производство",
        "weight": 2.9,
        "keywords": ["завод", "производ", "assembly", "factory", "plant", "manufactur"]
    },
    "electric": {
        "label": "Электромобили",
        "weight": 2.6,
        "keywords": ["ev", "electric", "электро", "battery", "charging", "зарядк"]
    },
    "gadgets": {
        "label": "Гаджеты",
        "weight": 2.55,
        "keywords": [
            "smartphone",
            "phone",
            "iphone",
            "android phone",
            "pixel",
            "galaxy",
            "tablet",
            "ipad",
            "laptop",
            "notebook",
            "ultrabook",
            "smartwatch",
            "watch",
            "wearable",
            "earbuds",
            "earphones",
            "headphones",
            "speaker",
            "camera",
            "drone",
            "vr headset",
            "ar glasses",
            "xr headset",
            "console",
            "gaming handheld",
            "display",
            "screen",
            "monitor",
            "router",
            "gadget",
            "device",
            "смартфон",
            "телефон",
            "планшет",
            "ноутбук",
            "часы",
            "наушник",
            "наушники",
            "камера",
            "дрон",
            "гарнитур",
            "диспле",
            "экран",
            "монитор",
            "роутер",
            "гаджет",
            "устройство"
        ]
    },
    "tips": {
        "label": "Лайфхаки",
        "weight": 2.5,
        "keywords": [
            "лайфхак",
            "совет",
            "советы",
            "как правильно",
            "как выбрать",
            "как подготовить",
            "что делать",
            "почему нельзя",
            "как продлить",
            "уход",
            "обслуживан",
            "maintenance",
            "checklist",
            "how to",
            "ownership tips",
            "winter prep",
            "summer prep"
        ]
    },
    "technology": {
        "label": "Технологии",
        "weight": 2.3,
        "keywords": [
            "software",
            "ai",
            "tech",
            "technology",
            "платформ",
            "chip",
            "chips",
            "processor",
            "gpu",
            "cpu",
            "semiconductor",
            "cloud",
            "developer",
            "api",
            "app",
            "apps",
            "open source",
            "robot",
            "robotics",
            "machine learning",
            "llm",
            "model",
            "assistant",
            "startup",
            "quantum",
            "cybersecurity",
            "security",
            "xr",
            "vr",
            "ar",
            "операционн",
            "софт",
            "технолог",
            "чип",
            "процессор",
            "нейросет",
            "робот",
            "облако",
            "разработч",
            "приложен",
            "модель",
            "ассистент",
            "безопасност"
        ]
    }
}
DEFAULT_TOPIC = ("industry", "Техноиндустрия", 1.7)
VEHICLE_HINT_KEYWORDS = (
    "smartphone",
    "phone",
    "tablet",
    "laptop",
    "watch",
    "earbuds",
    "headphones",
    "camera",
    "drone",
    "console",
    "смартфон",
    "планшет",
    "ноутбук",
    "часы",
    "наушники",
    "камера",
    "дрон"
)


def rank_candidates(
    items: List[CollectedItem],
    storage: Storage,
    allowed_topics: List[str],
    priority_topics: List[str],
    max_age_hours: int,
    min_age_minutes: int,
    max_items: int,
    diversity: DiversityConfig
) -> List[CandidateItem]:
    now = datetime.now(timezone.utc)
    fresh_after = now - timedelta(hours=max_age_hours)
    mature_before = now - timedelta(minutes=min_age_minutes)

    filtered = [
        item for item in items
        if fresh_after <= item.published_at <= mature_before
        and not storage.was_published(item.fingerprint)
    ]

    deduplicated = deduplicate(filtered)
    ranked: List[CandidateItem] = []
    topic_bonus = {topic: (len(priority_topics) - index) * 0.25 for index, topic in enumerate(priority_topics)}

    for group in deduplicated:
        best = max(group, key=lambda candidate: candidate.source_weight)
        topic, label, topic_weight = detect_topic(f"{best.title} {best.summary}")
        if allowed_topics and topic not in allowed_topics:
            continue
        assessment = assess_story(best, group, topic)
        if not assessment.should_publish:
            continue
        age_hours = max((now - best.published_at).total_seconds() / 3600, 0.0)
        freshness = max(0.0, 3.0 - math.log1p(age_hours))
        duplicates_bonus = 0.45 * (len(group) - 1)
        trust_bonus = {"high": 0.9, "medium": 0.35, "low": -0.6}.get(assessment.source_trust, 0.0)
        credibility_bonus = {"high": 0.8, "medium": 0.15, "low": -0.8}.get(assessment.credibility, 0.0)
        confirmation_bonus = min(0.25 * max(assessment.confirmation_count - 1, 0), 0.75)
        impact_bonus = min(assessment.impact_score * 0.12, 0.72)
        score = (
            topic_weight
            + freshness
            + best.source_weight
            + duplicates_bonus
            + topic_bonus.get(topic, 0.0)
            + trust_bonus
            + credibility_bonus
            + confirmation_bonus
            + impact_bonus
        )

        ranked.append(
            CandidateItem(
                source_name=best.source_name,
                source_group=best.source_group,
                source_language=best.source_language,
                source_weight=best.source_weight,
                source_kind=assessment.source_kind,
                source_trust=assessment.source_trust,
                source_in_registry=assessment.source_in_registry,
                title=best.title,
                summary=best.summary,
                url=best.url,
                image_url=best.image_url,
                published_at=best.published_at,
                topic=topic,
                topic_label=label,
                score=round(score, 3),
                duplicate_count=len(group),
                confirmation_count=assessment.confirmation_count,
                credibility=assessment.credibility,
                post_label=assessment.post_label,
                editorial_reason=assessment.reason,
                fingerprint=best.fingerprint,
                similar_urls=[item.url for item in group],
                video_url=best.video_url,
                original_title=best.title,
                original_summary=best.summary
            )
        )

    ranked.sort(key=lambda item: (item.score, item.published_at), reverse=True)
    if max_items <= 0:
        return []

    if not diversity.enabled:
        return ranked[:max_items]

    return diversify_candidates(ranked, diversity, max_items)


def deduplicate(items: List[CollectedItem]) -> List[List[CollectedItem]]:
    groups: List[List[CollectedItem]] = []

    for item in items:
        matched_group = None
        for group in groups:
            if any(is_same_story(item, existing) for existing in group):
                matched_group = group
                break

        if matched_group is None:
            groups.append([item])
        else:
            matched_group.append(item)

    return groups


def is_same_story(left: CollectedItem, right: CollectedItem) -> bool:
    if normalize_url(left.url) == normalize_url(right.url):
        return True

    similarity = SequenceMatcher(None, left.title_key, right.title_key).ratio()
    shared_tokens = len(set(left.tokens) & set(right.tokens))
    return similarity >= 0.92 or (similarity >= 0.82 and shared_tokens >= 4)


def detect_topic(text: str) -> Tuple[str, str, float]:
    lowered = text.lower()
    has_gadget_keywords = any(keyword in lowered for keyword in TOPIC_RULES["gadgets"]["keywords"])
    has_new_model_keywords = any(keyword in lowered for keyword in TOPIC_RULES["new_models"]["keywords"])
    has_technology_keywords = any(keyword in lowered for keyword in TOPIC_RULES["technology"]["keywords"])

    for topic in ("accidents", "recalls", "law"):
        rule = TOPIC_RULES[topic]
        if any(keyword in lowered for keyword in rule["keywords"]):
            return topic, rule["label"], float(rule["weight"])

    gadget_rule = TOPIC_RULES["gadgets"]
    if has_gadget_keywords:
        return "gadgets", gadget_rule["label"], float(gadget_rule["weight"])

    technology_rule = TOPIC_RULES["technology"]
    if has_technology_keywords:
        return "technology", technology_rule["label"], float(technology_rule["weight"])

    for topic in ("prices", "sales", "production"):
        rule = TOPIC_RULES[topic]
        if any(keyword in lowered for keyword in rule["keywords"]):
            return topic, rule["label"], float(rule["weight"])

    tips_rule = TOPIC_RULES["tips"]
    if any(keyword in lowered for keyword in tips_rule["keywords"]):
        return "tips", tips_rule["label"], float(tips_rule["weight"])

    new_models_rule = TOPIC_RULES["new_models"]
    if has_new_model_keywords:
        return "new_models", new_models_rule["label"], float(new_models_rule["weight"])

    for topic in ("electric",):
        rule = TOPIC_RULES[topic]
        if any(keyword in lowered for keyword in rule["keywords"]):
            return topic, rule["label"], float(rule["weight"])

    return DEFAULT_TOPIC


def diversify_candidates(
    ranked: List[CandidateItem],
    diversity: DiversityConfig,
    max_items: int
) -> List[CandidateItem]:
    selected: List[CandidateItem] = []
    remaining = list(ranked)
    publisher_counts: Counter[str] = Counter()
    topic_counts: Counter[str] = Counter()

    while remaining and len(selected) < max_items:
        strict_pool = [
            item for item in remaining
            if topic_counts[item.topic] < diversity.topic_limits.get(item.topic, max_items)
        ]
        if not strict_pool:
            break

        candidate_pool = strict_pool
        preferred_pool = [
            item for item in candidate_pool
            if publisher_counts[item.source_group] < diversity.max_per_publisher
            and topic_counts[item.topic] < diversity.max_per_topic
        ]
        candidate_pool = preferred_pool or candidate_pool

        chosen = max(
            candidate_pool,
            key=lambda item: (
                adjusted_score(item, publisher_counts, topic_counts, diversity),
                item.score,
                item.published_at_utc
            )
        )
        selected.append(chosen)
        remaining.remove(chosen)
        publisher_counts[chosen.source_group] += 1
        topic_counts[chosen.topic] += 1

    return selected


def adjusted_score(
    item: CandidateItem,
    publisher_counts: Counter[str],
    topic_counts: Counter[str],
    diversity: DiversityConfig
) -> float:
    return (
        item.score
        - (publisher_counts[item.source_group] * diversity.publisher_repeat_penalty)
        - (topic_counts[item.topic] * diversity.topic_repeat_penalty)
    )
