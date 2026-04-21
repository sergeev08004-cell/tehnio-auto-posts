from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import timezone
from urllib.parse import urlsplit

from news_bot.config import AppConfig
from news_bot.models import CandidateItem


MULTI_PUNCTUATION_RE = re.compile(r"[!?]+")
EXTRA_SPACE_RE = re.compile(r"\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
STRUCTURAL_PREFIX_RE = re.compile(r"^(?:коротко|что это значит|по сути|по фактам|по цифрам)\s*:\s*", re.IGNORECASE)
SUMMARY_ARTIFACT_RE = re.compile(
    r"\(?\s*(?:continue reading|read more|keep reading|продолжить чтение|читать далее|читать полностью)[^)\n]*\)?",
    re.IGNORECASE
)
EMPTY_PARENS_RE = re.compile(r"\(\s*\)")
CYRILLIC_CHAR_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_CHAR_RE = re.compile(r"[A-Za-z]")
HASHTAG_CLEAN_RE = re.compile(r"[^0-9A-Za-zА-Яа-яЁё]+")
PRICE_VALUE_RE = re.compile(
    r"((?:от|from)?\s*(?:[$€£¥₽₸]\s?\d[\d\s.,]*(?:\s?(?:k|m))?|\d[\d\s.,]*(?:\s?(?:тыс\.?|млн|k|m|million))?\s*"
    r"(?:руб(?:лей|ля|\.?)|₽|usd|доллар(?:ов|а)?|euros?|eur|евро|€|£|фунт(?:ов|а)?|pounds?|тенге|₸|yuan|юан(?:ей|я)?|¥|"
    r"(?:(?:australian|canadian|singapore|us|u\.s\.)\s+)?dollars?)))",
    re.IGNORECASE
)
SUMMARY_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+|(?<=[а-яё0-9])\s+(?=(?:В|На|По|Для|Однако|Также|Компания|В компании|Новинку|Новый|Это|При этом)\b)"
)
CLICKBAIT_REPLACEMENTS = (
    ("сенсация", ""),
    ("шок", ""),
    ("эксклюзив", ""),
    ("лучший", ""),
    ("худший", ""),
    ("невероятный", ""),
    ("unbelievable", ""),
    ("exclusive", ""),
    ("best", ""),
    ("worst", "")
)
RUSSIAN_MONTHS = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря"
}
TOPIC_EMOJIS = {
    "accidents": "🚨",
    "recalls": "⚠️",
    "law": "📜",
    "new_models": "🚀",
    "prices": "💵",
    "sales": "📈",
    "production": "🏭",
    "electric": "⚡",
    "gadgets": "📱",
    "tips": "🛠️",
    "technology": "🧠",
    "industry": "⚙️"
}
TOPIC_HASHTAGS = {
    "accidents": "ДТП",
    "recalls": "Отзыв",
    "law": "Регулирование",
    "new_models": "НоваяМодель",
    "prices": "Цены",
    "sales": "Рынок",
    "production": "Производство",
    "electric": "Энергия",
    "gadgets": "Гаджеты",
    "tips": "Лайфхаки",
    "technology": "Технологии",
    "industry": "ТехноНовости"
}
GADGET_HASHTAG_RULES = (
    ("copilot", "Copilot"),
    ("iphone", "iPhone"),
    ("android", "Android"),
    ("pixel", "Pixel"),
    ("galaxy", "Galaxy"),
    ("smartphone", "Смартфоны"),
    ("tablet", "Планшеты"),
    ("ipad", "iPad"),
    ("laptop", "Ноутбуки"),
    ("notebook", "Ноутбуки"),
    ("earbuds", "Наушники"),
    ("headphones", "Наушники"),
    ("smartwatch", "СмартЧасы"),
    ("wearable", "Wearables"),
    ("camera", "Камеры"),
    ("drone", "Дроны"),
    ("console", "Консоли"),
    ("robotics", "Роботы"),
    ("robot", "Роботы"),
    ("робот", "Роботы"),
    ("vr", "VR"),
    ("ar", "AR"),
    ("xr", "XR"),
    ("charger", "Зарядка"),
    ("зарядн", "Зарядка"),
    ("screen", "Дисплеи"),
    ("display", "Дисплеи"),
    ("экран", "Дисплеи"),
    ("диспле", "Дисплеи"),
    ("camera", "Камеры"),
    ("камера", "Камеры"),
    ("ai", "AI"),
    ("chip", "Чипы"),
    ("assistant", "AI"),
    ("processor", "Процессоры")
)
BRAND_TAGS = (
    ("apple", "Apple"),
    ("google", "Google"),
    ("samsung", "Samsung"),
    ("microsoft", "Microsoft"),
    ("meta", "Meta"),
    ("amazon", "Amazon"),
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("nvidia", "NVIDIA"),
    ("amd", "AMD"),
    ("intel", "Intel"),
    ("qualcomm", "Qualcomm"),
    ("sony", "Sony"),
    ("xiaomi", "Xiaomi"),
    ("huawei", "Huawei"),
    ("honor", "Honor"),
    ("nothing", "Nothing"),
    ("oneplus", "OnePlus"),
    ("lenovo", "Lenovo"),
    ("asus", "ASUS"),
    ("acer", "Acer"),
    ("dell", "Dell"),
    ("hp", "HP"),
    ("logitech", "Logitech"),
    ("dji", "DJI"),
    ("garmin", "Garmin"),
    ("beats", "Beats"),
    ("bose", "Bose"),
    ("anker", "Anker"),
    ("sonos", "Sonos")
)
SOURCE_TAGS = {
    "techcrunch": "TechCrunch",
    "google": "Google",
    "apple": "Apple",
    "samsung": "Samsung",
    "openai": "OpenAI",
    "garmin": "Garmin"
}
SPEC_FOCUS_TOPICS = {"gadgets", "technology"}
GADGET_KEYWORDS = (
    "гаджет",
    "устройств",
    "девайс",
    "аксессуар",
    "смартфон",
    "телефон",
    "tablet",
    "планшет",
    "laptop",
    "ноутбук",
    "smartwatch",
    "watch",
    "wearable",
    "earbuds",
    "headphones",
    "камера",
    "camera",
    "drone",
    "vr",
    "ar",
    "xr",
    "экран",
    "диспле",
    "display",
    "screen",
    "зарядн",
    "charger",
    "адаптер",
    "speaker",
    "router",
    "console"
)
MODEL_KEYWORDS = (
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
TITLE_SUBJECT_PATTERNS = (
    re.compile(
        r"\b(?P<value>смартфон|планшет|ноутбук|смарт-часы|умные часы|наушники|камера|дрон|консоль|vr[- ]гарнитура|"
        r"ar[- ]очки|xr[- ]гарнитура|чип|процессор|ai[- ]ассистент|мультимедийн(?:ый|ая|ое)\s+экран|дисплей)\b",
        re.IGNORECASE
    ),
    re.compile(
        r"\b(?P<value>(?:(?:нов(?:ый|ая|ое)|флагманск(?:ий|ая|ое)|обновленн(?:ый|ая|ое)|перв(?:ый|ая|ое))\s+){0,2}"
        r"(?:смартфон|планшет|ноутбук|чип|процессор|гарнитура|модель|девайс|gadget|device))\b",
        re.IGNORECASE
    ),
    re.compile(
        r"\b(?P<value>производитель|компания|бренд|разработчик|команда)\b",
        re.IGNORECASE
    ),
    re.compile(
        r"\b(?P<value>гаджет|смартфон|ноутбук|технология|ai|чип|платформа|приложение)\b",
        re.IGNORECASE
    )
)
POWER_RE = re.compile(r"(?P<value>\d{2,4}(?:[.,]\d+)?)\s*(?P<unit>л\.?\s*с\.?|hp|bhp|кВт|kw)\b", re.IGNORECASE)
BATTERY_RE = re.compile(r"(?P<value>\d{1,3}(?:[.,]\d+)?)\s*(?P<unit>кВт(?:·|-|\s)?ч|kwh)\b", re.IGNORECASE)
RANGE_PATTERNS = (
    re.compile(
        r"(?:запас(?:ом)? хода|range|wltp|epa|cltc|пробег(?:а)?)(?:[^0-9]{0,24})(?P<value>\d{2,4})\s*(?P<unit>км|km)\b",
        re.IGNORECASE
    ),
    re.compile(
        r"(?P<value>\d{2,4})\s*(?P<unit>км|km)\b(?:[^0-9]{0,24})(?:запас(?:ом)? хода|range|wltp|epa|cltc|пробег(?:а)?)",
        re.IGNORECASE
    )
)
ACCELERATION_RE = re.compile(
    r"0\s*[-–—]\s*100\s*(?:км/ч|km/h)?\s*(?:за|in)?\s*(?P<value>\d{1,2}(?:[.,]\d+)?)\s*(?:с|секунд\w*|sec|seconds)\b",
    re.IGNORECASE
)
CHARGING_PATTERNS = (
    re.compile(
        r"(?:зарядк\w*|charging(?: power)?|dc fast|быстр\w* заряд\w*)(?:[^0-9]{0,24})(?P<value>\d{2,4}(?:[.,]\d+)?)\s*(?:кВт|kw)\b",
        re.IGNORECASE
    ),
    re.compile(
        r"(?P<value>\d{2,4}(?:[.,]\d+)?)\s*(?:кВт|kw)\b(?:[^0-9]{0,24})(?:зарядк\w*|charging(?: power)?|dc fast|быстр\w* заряд\w*)",
        re.IGNORECASE
    )
)
TORQUE_RE = re.compile(r"(?P<value>\d{2,4}(?:[.,]\d+)?)\s*(?:Нм|nm)\b", re.IGNORECASE)
ENGINE_PATTERNS = (
    re.compile(
        r"(?:двигател\w*|turbo|motor|v6|v8|рядн\w*)(?:[^0-9]{0,20})(?P<value>\d(?:[.,]\d)?)\s*(?:л|литр\w*)\b",
        re.IGNORECASE
    ),
    re.compile(
        r"(?P<value>\d(?:[.,]\d)?)\s*(?:л|литр\w*)\b(?:[^0-9]{0,20})(?:двигател\w*|turbo|motor|v6|v8|рядн\w*)",
        re.IGNORECASE
    )
)
SCREEN_PATTERNS = (
    re.compile(
        r"(?:экран|диспле\w*|display|screen)(?:[^0-9]{0,20})(?P<value>\d{1,2}(?:[.,]\d+)?)\s*(?:дюйм(?:а|ов)?|inch(?:es)?|\")",
        re.IGNORECASE
    ),
    re.compile(
        r"(?P<value>\d{1,2}(?:[.,]\d+)?)\s*(?:дюйм(?:а|ов)?|inch(?:es)?|\")(?:[^0-9]{0,20})(?:экран|диспле\w*|display|screen)",
        re.IGNORECASE
    )
)
MEMORY_PATTERNS = (
    re.compile(
        r"(?:памят\w*|storage|ram|оператив\w*)(?:[^0-9]{0,20})(?P<value>\d{1,4})\s*(?P<unit>ГБ|GB|ТБ|TB)\b",
        re.IGNORECASE
    ),
    re.compile(
        r"(?P<value>\d{1,4})\s*(?P<unit>ГБ|GB|ТБ|TB)\b(?:[^0-9]{0,20})(?:памят\w*|storage|ram|оператив\w*)",
        re.IGNORECASE
    )
)
VOLTAGE_PATTERNS = (
    re.compile(
        r"(?:архитектур\w*|систем\w*|platform|charging)(?:[^0-9]{0,20})(?P<value>\d{2,4})\s*(?:В|V|volt(?:s)?|вольт\w*)\b",
        re.IGNORECASE
    ),
    re.compile(
        r"(?P<value>\d{2,4})\s*(?:В|V|volt(?:s)?|вольт\w*)\b(?:[^0-9]{0,20})(?:архитектур\w*|систем\w*|platform|charging)",
        re.IGNORECASE
    )
)
CAMERA_PATTERNS = (
    re.compile(
        r"(?:камера|camera)(?:[^0-9]{0,20})(?P<value>\d{1,3}(?:[.,]\d+)?)\s*(?:Мп|MP)\b",
        re.IGNORECASE
    ),
    re.compile(
        r"(?P<value>\d{1,3}(?:[.,]\d+)?)\s*(?:Мп|MP)\b(?:[^0-9]{0,20})(?:камера|camera)",
        re.IGNORECASE
    )
)
PRICE_PATTERNS = (
    re.compile(
        r"(?:цен\w*|стоимост\w*|price(?:d)?|pricing|costs?|costing|starts?\s+at|starting\s+at|from)(?:[^0-9$€£¥₽₸]{0,18})"
        r"(?P<value>(?:от|from)?\s*(?:[$€£¥₽₸]\s?\d[\d\s.,]*(?:\s?(?:k|m))?|\d[\d\s.,]*(?:\s?(?:тыс\.?|млн|k|m|million))?\s*"
        r"(?:руб(?:лей|ля|\.?)|₽|usd|доллар(?:ов|а)?|euros?|eur|евро|€|£|фунт(?:ов|а)?|pounds?|тенге|₸|yuan|юан(?:ей|я)?|¥|"
        r"(?:(?:australian|canadian|singapore|us|u\.s\.)\s+)?dollars?)))",
        re.IGNORECASE
    ),
)
MODEL_STOPWORDS = {
    "обновила",
    "обновил",
    "представила",
    "представил",
    "показала",
    "показал",
    "раскрыла",
    "раскрыл",
    "сообщила",
    "сообщил",
    "запустила",
    "запустил",
    "получила",
    "получил",
    "получили",
    "получит",
    "получат",
    "вышла",
    "вышел",
    "вышли",
    "объявила",
    "объявил",
    "стартовали",
    "начались",
    "стартовал",
    "получает",
    "получают",
    "to",
    "for",
    "gets",
    "get",
    "gains",
    "gain",
    "debuts",
    "debuts,"
}
MODEL_BRAND_PATTERN = "|".join(
    sorted((re.escape(phrase) for phrase, _ in BRAND_TAGS), key=len, reverse=True)
)
MODEL_MENTION_RE = re.compile(
    rf"\b(?P<brand>{MODEL_BRAND_PATTERN})(?P<tail>(?:\s+[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9+/.\-]*){{1,4}})",
    re.IGNORECASE
)
GENERIC_HEADLINE_SUBJECTS = {
    "технология",
    "бренд",
    "новинка",
    "устройство",
    "модель",
    "девайс",
}
HEADLINE_SHORT_TOKEN_ALLOWLIST = {"ai", "vr", "ar", "xr", "x", "tv", "в", "с", "к", "и"}
GENERIC_TAKEAWAY_KEYS = {
    "это показывает какие технологии быстрее всего доходят до массовых устройств и сервисов",
    "такие обновления напрямую влияют на повседневный цифровой опыт пользователя",
    "это ранний сигнал о том куда бренд двигает продуктовую линейку",
}
GENERIC_INTERESTING_KEYS = {
    "история выглядит интереснее чем обычный заголовок",
    "всё может упереться в спрос цену и позиционирование",
    "ключевые детали уже видны по цифрам",
}


@dataclass(frozen=True)
class NewsAnalysis:
    title_text: str
    subject: str
    core: str
    interesting: str
    numbers: list[str]
    angle: str
    story_points: list[str]
    specs: list[str]
    price_line: str
    takeaway: str


@dataclass(frozen=True)
class PostVariant:
    headline: str
    paragraphs: list[str]
    headline_score: int
    curiosity_score: int
    emotion_score: int

    @property
    def total_score(self) -> int:
        return self.headline_score + self.curiosity_score + self.emotion_score


def format_post(item: CandidateItem, config: AppConfig, channel_id: str = "") -> str:
    return _format_post(
        item,
        config=config,
        channel_id=channel_id,
        summary_limit=2200,
        max_length=4096,
        max_bullets=5,
        include_spoiler=True
    )


def format_caption(item: CandidateItem, config: AppConfig, channel_id: str = "") -> str:
    return _format_post(
        item,
        config=config,
        channel_id=channel_id,
        summary_limit=900,
        max_length=1024,
        max_bullets=3,
        include_spoiler=False
    )


def _format_post(
    item: CandidateItem,
    config: AppConfig,
    channel_id: str,
    summary_limit: int,
    max_length: int,
    max_bullets: int,
    include_spoiler: bool
) -> str:
    title = neutralize_headline(item.title)
    summary = truncate_story_text(item.summary, summary_limit)
    compact = not include_spoiler or max_length <= 1024
    analysis = analyze_news_item(item, title, summary, compact=compact)
    variants = build_post_variants(item, title, analysis, compact=compact)
    best_variant = choose_best_variant(variants)
    if config.editorial.profile.lower() == "tehnio":
        return render_tehnio_post(best_variant, item, analysis, config=config, max_length=max_length, compact=compact)
    return render_post_variant(best_variant, item, config=config, max_length=max_length)


def analyze_news_item(item: CandidateItem, title: str, summary: str, compact: bool) -> NewsAnalysis:
    story_points = collect_story_points(title, summary, max_points=4 if not compact else 3)
    lead = story_points[0] if story_points else ""
    core = choose_core_sentence(title, lead, story_points)
    specs = extract_spec_highlights(item, title, summary, max_specs=3 if not compact else 2)
    price_lines = build_price_lines(item, title, summary, max_lines=1)
    price_line = price_lines[0] if price_lines else ""
    numbers = collect_number_facts(item, title, summary, max_items=3 if not compact else 2)
    interesting = choose_interesting_detail(
        item,
        title,
        summary,
        story_points,
        numbers,
        core,
        specs,
        price_line
    )
    angle = detect_post_angle(item, title, summary, numbers)
    subject = extract_subject_label(item, title, summary)
    takeaway = build_takeaway_line(
        item,
        title,
        summary,
        has_specs=bool(specs),
        has_price=bool(price_line)
    )
    return NewsAnalysis(
        title_text=title,
        subject=subject,
        core=core,
        interesting=interesting,
        numbers=numbers,
        angle=angle,
        story_points=story_points,
        specs=specs,
        price_line=price_line,
        takeaway=takeaway
    )


def build_post_variants(item: CandidateItem, title: str, analysis: NewsAnalysis, compact: bool) -> list[PostVariant]:
    strategies = ("factual", "detail", "impact")
    variants = []
    for strategy in strategies:
        headline = build_variant_headline(title, analysis, strategy)
        paragraphs = build_variant_paragraphs(item, analysis, strategy, compact=compact)
        headline_score, curiosity_score, emotion_score = score_post_variant(
            title,
            headline,
            paragraphs,
            analysis,
            strategy
        )
        variants.append(
            PostVariant(
                headline=headline,
                paragraphs=paragraphs,
                headline_score=headline_score,
                curiosity_score=curiosity_score,
                emotion_score=emotion_score
            )
        )
    return variants


def choose_best_variant(variants: list[PostVariant]) -> PostVariant:
    return max(
        variants,
        key=lambda item: (
            item.total_score,
            item.headline_score,
            item.curiosity_score,
            item.emotion_score
        )
    )


def render_post_variant(variant: PostVariant, item: CandidateItem, config: AppConfig, max_length: int) -> str:
    body = list(variant.paragraphs)
    hashtags = build_hashtags(item, variant.headline)
    while body:
        text = compose_post_text(variant.headline, body, item.url, item, hashtags, config)
        if len(text) <= max_length:
            return text
        if len(body) > 2:
            body.pop()
            continue
        shortened = [truncate(paragraph, 150 if index == 0 else 130) for index, paragraph in enumerate(body)]
        text = compose_post_text(variant.headline, shortened, item.url, item, hashtags[:4], config)
        if len(text) <= max_length:
            return text
        body = shortened[:-1] or shortened
        if len(body) == 1:
            break

    fallback_headline = truncate(variant.headline, 70)
    fallback_body = [truncate(variant.paragraphs[0], 150)] if variant.paragraphs else []
    return compose_post_text(fallback_headline, fallback_body, item.url, item, hashtags[:3], config)


def compose_post_text(
    headline: str,
    paragraphs: list[str],
    url: str,
    item: CandidateItem,
    hashtags: list[str],
    config: AppConfig
) -> str:
    lines = [build_headline(item, headline, config), ""]
    for paragraph in paragraphs:
        clean = paragraph.strip()
        if not clean:
            continue
        lines.append(escape_text(clean))
    persona_lines = render_persona_comments(item, config)
    if persona_lines:
        lines.extend(["", *persona_lines])
    lines.extend(["", build_story_link(url, config)])
    if hashtags:
        lines.extend(["", render_hashtags(hashtags)])
    subscribe_cta = build_subscribe_cta(config)
    if subscribe_cta:
        lines.extend(["", subscribe_cta])
    return "\n".join(lines).strip()


def render_tehnio_post(
    variant: PostVariant,
    item: CandidateItem,
    analysis: NewsAnalysis,
    config: AppConfig,
    max_length: int,
    compact: bool
) -> str:
    intro_paragraphs = build_tehnio_intro_paragraphs(item, analysis, compact=compact)
    facts = build_tehnio_fact_lines(item, analysis, max_items=3 if compact else 4)
    hashtags = build_tehnio_hashtags(item, analysis, max_items=6 if compact else 9)
    headline = build_tehnio_headline(item, analysis, variant.headline)

    while True:
        text = compose_tehnio_post_text(headline, intro_paragraphs, facts, item, hashtags, config)
        if len(text) <= max_length:
            return text
        if len(facts) > 2:
            facts = facts[:-1]
            continue
        if len(hashtags) > 5:
            hashtags = hashtags[:-1]
            continue
        if len(intro_paragraphs) > 1:
            intro_paragraphs = intro_paragraphs[:1]
            continue
        shortened = [truncate(paragraph, 180 if index == 0 else 130) for index, paragraph in enumerate(intro_paragraphs)]
        return compose_tehnio_post_text(headline, shortened, facts[:2], item, hashtags[:5], config)


def compose_tehnio_post_text(
    headline: str,
    intro_paragraphs: list[str],
    facts: list[str],
    item: CandidateItem,
    hashtags: list[str],
    config: AppConfig
) -> str:
    lines = [build_headline(item, headline, config), ""]
    for paragraph in intro_paragraphs:
        clean = paragraph.strip()
        if clean:
            lines.append(escape_text(clean))

    if facts:
        lines.extend(["", "📌 <b>Что известно:</b>"])
        for fact in facts:
            lines.append(f"— {escape_text(fact)}")

    persona_lines = render_tehnio_persona(item)
    if persona_lines:
        lines.extend(["", *persona_lines])

    lines.extend(["", build_story_link(item.url, config)])

    if hashtags:
        lines.extend(["", render_tehnio_hashtags(hashtags)])

    subscribe_cta = build_subscribe_cta(config)
    if subscribe_cta:
        lines.extend(["", subscribe_cta])
    return "\n".join(lines).strip()


def collect_story_points(title: str, summary: str, max_points: int) -> list[str]:
    points: list[str] = []
    seen: set[str] = {comparable_text_key(title)} if title else set()

    for sentence in split_story_sentences(summary, max_items=max_points + 3):
        clean = normalize_analysis_sentence(sentence, limit=210)
        if not clean:
            continue
        key = comparable_text_key(clean)
        if key in seen:
            continue
        seen.add(key)
        points.append(clean)
        if len(points) >= max_points:
            break

    if not points:
        fallback = normalize_analysis_sentence(title, limit=160)
        if fallback:
            points.append(fallback)

    return points


def split_story_sentences(summary: str, max_items: int) -> list[str]:
    sentences: list[str] = []
    raw_paragraphs = [part.strip() for part in re.split(r"\n{2,}", summary) if part.strip()]
    if not raw_paragraphs:
        raw_paragraphs = [summary]

    for raw_paragraph in raw_paragraphs:
        for part in SUMMARY_SPLIT_RE.split(raw_paragraph):
            clean = normalize_analysis_sentence(part, limit=280)
            if not clean:
                continue
            sentences.append(clean)
            if len(sentences) >= max_items:
                return sentences

    return sentences[:max_items]


def choose_core_sentence(title: str, lead: str, story_sentences: list[str]) -> str:
    candidates = [lead, *story_sentences, title]
    title_key = comparable_text_key(title)
    for candidate in candidates:
        clean = simplify_core_sentence(normalize_analysis_sentence(candidate))
        if not clean:
            continue
        if comparable_text_key(clean) == title_key and candidate != title:
            continue
        return clean
    return simplify_core_sentence(normalize_analysis_sentence(title)) or "Тут появилась заметная история в технологиях."


def choose_interesting_detail(
    item: CandidateItem,
    title: str,
    summary: str,
    story_points: list[str],
    numbers: list[str],
    core: str,
    specs: list[str],
    price_line: str
) -> str:
    if price_line:
        return f"Цена стартует с {price_line}"

    concrete_story = first_distinct_sentence(story_points[1:], exclude=[title, core])
    if concrete_story:
        return sentence_to_clause(concrete_story)

    if specs:
        return f"По характеристикам здесь есть что показать: {', '.join(spec_to_sentence_fragment(spec) for spec in specs[:2])}"

    if numbers:
        return f"Ключевые детали уже видны по цифрам: {', '.join(numbers[:2])}"

    if item.topic == "recalls":
        return "это уже история, которая может задеть пользователей напрямую"
    if item.topic == "law":
        return "тут всё может быстро упереться в новые правила для водителей"
    if item.topic == "accidents":
        return "в этой истории есть явный нерв и вопрос безопасности"
    if item.topic in {"sales", "prices", "production", "industry"}:
        return "всё может упереться в спрос, цену и позиционирование"

    return ""


def collect_number_facts(item: CandidateItem, title: str, summary: str, max_items: int) -> list[str]:
    facts: list[str] = []
    seen: set[str] = set()

    price_lines = build_price_lines(item, title, summary, max_lines=2)
    for price in price_lines:
        normalized = f"цена {price}".strip()
        key = normalized.lower()
        if key not in seen:
            seen.add(key)
            facts.append(normalized)

    for spec in extract_spec_highlights(item, title, summary, max_specs=max_items + 1):
        key = spec.lower()
        if key in seen:
            continue
        seen.add(key)
        facts.append(spec)

    return facts[:max_items]


def detect_post_angle(item: CandidateItem, title: str, summary: str, numbers: list[str]) -> str:
    lowered = f"{title} {summary}".lower()
    if item.topic in {"recalls", "law", "accidents"}:
        return "tension"
    if item.topic in {"prices", "sales", "production", "industry"}:
        return "benefit"
    if item.topic in {"new_models", "electric", "technology", "gadgets"} or numbers:
        return "technology"
    if any(keyword in lowered for keyword in ("впервые", "first", "unexpected", "неожиданно")):
        return "unexpected"
    return "unexpected"


def extract_subject_label(item: CandidateItem, title: str, summary: str) -> str:
    combined = f"{title}. {summary}"
    mentions = extract_model_mentions(combined)
    if mentions:
        return shorten_subject(mentions[0][0])

    for pattern in TITLE_SUBJECT_PATTERNS:
        match = pattern.search(title)
        if match:
            return shorten_subject(match.group("value"))

    lowered = combined.lower()
    for phrase, _tag in BRAND_TAGS:
        if phrase_in_text(lowered, phrase):
            return shorten_subject(prettify_subject_phrase(phrase))

    if item.topic in {"new_models", "electric"}:
        return "новинка"
    if item.topic in {"recalls", "law"}:
        return "бренд"
    if item.topic in {"technology", "gadgets"}:
        return "технология"

    source_word = (item.source_name or "бренд").split()[0]
    return shorten_subject(source_word)


def shorten_subject(value: str, max_words: int = 3) -> str:
    tokens = [token for token in re.split(r"\s+", value.strip()) if token]
    if not tokens:
        return "бренд"
    return " ".join(tokens[:max_words])


def prettify_subject_phrase(value: str) -> str:
    parts = re.split(r"[\s-]+", value.strip())
    normalized = []
    for part in parts:
        if not part:
            continue
        if part.isupper() or len(part) <= 3:
            normalized.append(part.upper())
        else:
            normalized.append(part.capitalize())
    return " ".join(normalized)


def first_distinct_sentence(candidates: list[str], exclude: list[str]) -> str:
    excluded = {comparable_text_key(value) for value in exclude if value}
    for candidate in candidates:
        clean = normalize_analysis_sentence(candidate)
        if not clean:
            continue
        if comparable_text_key(clean) in excluded:
            continue
        return clean
    return ""


def sentence_to_clause(value: str) -> str:
    clean = normalize_analysis_sentence(value)
    if not clean:
        return ""
    clean = clean.rstrip(".")
    if not clean:
        return ""
    return clean[0].lower() + clean[1:]


def normalize_analysis_sentence(value: str, limit: int = 240) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    clean = neutralize_text(raw).strip()
    clean = re.sub(r"\s*[;:]\s*", ", ", clean)
    clean = EXTRA_SPACE_RE.sub(" ", clean).strip(" .")
    if not clean:
        return ""
    if len(clean) > limit:
        clean = truncate(clean, limit)
    if clean.endswith("..."):
        return clean
    return clean.rstrip(".")


def simplify_core_sentence(value: str) -> str:
    clean = (value or "").strip()
    if not clean:
        return ""

    if ":" in clean:
        head, tail = clean.split(":", 1)
        if sum(character.isdigit() for character in tail) >= 2 or tail.count(",") >= 2:
            clean = head.strip()

    if clean.count(",") >= 3 and sum(character.isdigit() for character in clean) >= 2:
        if ". " in clean:
            clean = clean.split(". ", 1)[0].strip()
        else:
            clean = clean.split(",", 1)[0].strip()

    if clean.endswith("..."):
        return clean
    return clean.rstrip(".")


def build_variant_headline(title: str, analysis: NewsAnalysis, strategy: str) -> str:
    factual_headline = compress_title_headline(title)
    if strategy == "factual":
        return factual_headline

    if strategy == "detail":
        detail_headline = build_fact_driven_headline(analysis)
        if detail_headline:
            return detail_headline
        return factual_headline

    impact_headline = build_impact_headline(analysis)
    if headline_is_usable(impact_headline, title):
        return impact_headline
    return factual_headline


def fit_headline_to_limit(value: str, max_words: int) -> str:
    words = value.split()
    if len(words) <= max_words:
        return value.strip()
    return " ".join(words[:max_words]).strip(" ,.;:-")


def build_variant_paragraphs(item: CandidateItem, analysis: NewsAnalysis, strategy: str, compact: bool) -> list[str]:
    detail_point = first_distinct_sentence(analysis.story_points[1:], exclude=[analysis.core, analysis.title_text])
    context_point = first_distinct_sentence(
        analysis.story_points[2:] if detail_point else analysis.story_points[1:],
        exclude=[analysis.core, analysis.title_text, detail_point, analysis.interesting, analysis.takeaway]
    )
    summary_paragraph = build_summary_paragraph(item, analysis, detail_point, context_point)
    importance_paragraph = build_importance_paragraph(item, analysis, detail_point, context_point)
    facts_paragraph = build_fact_paragraph(analysis, detail_point, context_point)

    if strategy == "factual":
        paragraphs = [summary_paragraph, importance_paragraph, facts_paragraph]
    elif strategy == "detail":
        paragraphs = [summary_paragraph, importance_paragraph, facts_paragraph]
    else:
        paragraphs = [summary_paragraph, importance_paragraph, build_impact_paragraph(analysis, detail_point)]

    cleaned = unique_paragraphs(paragraphs, max_items=3 if not compact else 2)
    if not compact and len(cleaned) < 2 and facts_paragraph:
        cleaned = unique_paragraphs([summary_paragraph, facts_paragraph], max_items=3)
    return cleaned[:3] if not compact else cleaned[:2]


def build_evidence_paragraph(analysis: NewsAnalysis, item: CandidateItem) -> str:
    if analysis.numbers:
        return ", ".join(analysis.numbers[:3])
    if item.topic == "recalls":
        return "здесь уже есть конкретный продуктовый повод для обсуждения"
    if item.topic == "law":
        return "тема напрямую касается правил и того, как ездить дальше"
    if item.topic == "accidents":
        return "здесь всё крутится вокруг безопасности и последствий на дороге"
    if item.topic in {"new_models", "electric", "technology", "gadgets"}:
        return "в фокусе характеристики, а не просто красивый анонс"
    return "история уже выглядит заметной даже без лишнего шума"


def normalize_body_paragraph(value: str, limit: int = 180) -> str:
    clean = EXTRA_SPACE_RE.sub(" ", value.strip())
    clean = re.sub(r"\s+\.", ".", clean)
    clean = re.sub(r"\.\.", ".", clean)
    clean = clean.strip(" .")
    if not clean:
        return ""
    if len(clean) > limit:
        clean = truncate(clean, limit)
    if clean.endswith("..."):
        return clean
    return clean.rstrip(".") + "."


def unique_paragraphs(paragraphs: list[str], max_items: int) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for paragraph in paragraphs:
        clean = normalize_body_paragraph(paragraph)
        if not clean:
            continue
        key = comparable_text_key(clean)
        if key in seen:
            continue
        seen.add(key)
        unique.append(clean)
        if len(unique) >= max_items:
            break
    return unique


def build_numbers_paragraph(analysis: NewsAnalysis) -> str:
    if not analysis.numbers:
        return ""
    return facts_sentence_from_items(analysis.numbers[:2])


def build_takeaway_paragraph(analysis: NewsAnalysis) -> str:
    takeaway = normalize_analysis_sentence(analysis.takeaway, limit=140)
    lowered_takeaway = takeaway.lower().replace(",", "")
    if any(lowered_takeaway.startswith(prefix) for prefix in GENERIC_TAKEAWAY_KEYS):
        return ""
    return takeaway


def build_summary_paragraph(
    item: CandidateItem,
    analysis: NewsAnalysis,
    detail_point: str,
    context_point: str
) -> str:
    haystack = " ".join(
        part for part in [
            analysis.title_text,
            analysis.core,
            detail_point,
            context_point,
            analysis.interesting,
        ]
        if part
    ).lower()

    if any(keyword in haystack for keyword in ("terms of service", "условия использования", "copilot")) and any(
        keyword in haystack for keyword in ("trust", "не довер", "развлекательных целей", "entertainment purposes")
    ):
        return "Microsoft прямо прописала, что Copilot нельзя воспринимать как надежный источник."

    if any(keyword in haystack for keyword in ("suno", "copyright", "ai music", "covers")):
        return "Suno упростила выпуск AI-каверов известных треков."

    if all(keyword in haystack for keyword in ("openai",)) and any(
        keyword in haystack for keyword in ("brockman", "брокман")
    ) and any(
        keyword in haystack for keyword in ("medical leave", "leave", "отпуск", "по болезни")
    ):
        return "Пока Фиджи Симо в отпуске, продукт OpenAI временно переходит к Грегу Брокману."

    if any(keyword in haystack for keyword in ("sony", "ps5", "playstation")) and analysis.price_line:
        return f"Sony подняла цену PS5 до {analysis.price_line}."

    if any(keyword in haystack for keyword in ("robot", "robotics", "робот", "physical ai", "физический ии")):
        if "япони" in haystack:
            return "Япония переводит физический AI из тестов в реальную работу на заводах и складах."
        return "Физический AI начинает выходить из пилотов в реальный бизнес."

    if analysis.price_line and any(keyword in haystack for keyword in ("price", "pricing", "цена", "подорож")):
        return f"В центре новости оказалась цена {analysis.price_line}."

    source = first_non_generic_text(analysis.core, detail_point, context_point, analysis.interesting)
    summary_line = summary_line_from_text(source)
    if summary_line:
        return summary_line
    return build_generic_summary_paragraph(item, analysis)


def build_importance_paragraph(
    item: CandidateItem,
    analysis: NewsAnalysis,
    detail_point: str,
    context_point: str
) -> str:
    haystack = " ".join(
        part for part in [
            analysis.title_text,
            analysis.core,
            analysis.interesting,
            detail_point,
            context_point,
            analysis.takeaway,
        ]
        if part
    ).lower()

    if any(keyword in haystack for keyword in ("terms of service", "условия использования", "не довер", "trust")):
        return "Даже сама компания предупреждает, что ответам AI нельзя доверять вслепую."

    if any(keyword in haystack for keyword in ("suno", "copyright", "ai music", "covers")):
        return "Из-за этого спор вокруг AI-музыки теперь сильнее ударит по авторам и стримингам."

    if all(keyword in haystack for keyword in ("openai",)) and any(
        keyword in haystack for keyword in ("brockman", "брокман")
    ) and any(
        keyword in haystack for keyword in ("medical leave", "leave", "отпуск", "по болезни")
    ):
        return "Для OpenAI это чувствительный момент, потому что продукт снова оказывается в руках одного из ключевых людей компании."

    if any(keyword in haystack for keyword in ("sony", "ps5", "playstation")) and analysis.price_line:
        return "Это показывает, что рынок консолей все еще не готов возвращаться к прежним ценам."

    if any(keyword in haystack for keyword in ("robot", "robotics", "робот", "physical ai", "физический ии")):
        return "Для рынка это сигнал, что AI выходит из тестов и заходит в реальный бизнес."

    if analysis.price_line:
        return "По этой цене уже видно, как бренд позиционирует новинку."

    if analysis.specs:
        return "По характеристикам уже видно, что именно получит пользователь."

    takeaway = build_takeaway_paragraph(analysis)
    if takeaway:
        importance_line = impact_line_from_text(takeaway)
        if importance_line:
            return importance_line

    fallback = normalize_analysis_sentence(context_point or detail_point or analysis.interesting, limit=130)
    if fallback:
        importance_line = impact_line_from_text(fallback)
        if importance_line:
            return importance_line

    if item.topic in {"gadgets", "technology"}:
        return "Такие изменения обычно быстро доходят до обычных пользователей и сервисов."

    return build_generic_importance_paragraph(item, analysis)


def build_impact_paragraph(analysis: NewsAnalysis, detail_point: str) -> str:
    if detail_point:
        candidate = normalize_analysis_sentence(detail_point, limit=115)
        if candidate and (any(character.isdigit() for character in candidate) or (len(candidate) <= 100 and candidate.count(",") == 0)):
            detail_line = summary_line_from_text(candidate)
            if detail_line:
                return detail_line
    if analysis.specs:
        specs_line = facts_sentence_from_items(analysis.specs[:2])
        if specs_line:
            return specs_line
    numbers_line = build_numbers_paragraph(analysis)
    if numbers_line:
        return numbers_line
    fallback = normalize_analysis_sentence(analysis.interesting, limit=110)
    if fallback and (any(character.isdigit() for character in fallback) or (len(fallback) <= 100 and fallback.count(",") == 0)):
        return summary_line_from_text(fallback)
    return ""


def summary_line_from_text(value: str, prefix: str = "Коротко") -> str:
    return normalize_explainer_sentence(value, limit=130)


def impact_line_from_text(value: str) -> str:
    return normalize_explainer_sentence(value, limit=130)


def build_fact_paragraph(analysis: NewsAnalysis, detail_point: str, context_point: str) -> str:
    candidate = normalize_analysis_sentence(detail_point or context_point, limit=115)
    if candidate and (any(character.isdigit() for character in candidate) or (len(candidate) <= 100 and candidate.count(",") == 0)):
        detail_line = summary_line_from_text(candidate)
        if detail_line:
            return detail_line
    if analysis.specs:
        specs_line = facts_sentence_from_items(analysis.specs[:2])
        if specs_line:
            return specs_line
    return build_numbers_paragraph(analysis)


def normalize_explainer_sentence(value: str, limit: int = 130) -> str:
    clean = normalize_analysis_sentence(value, limit=limit)
    if not clean:
        return ""
    clean = STRUCTURAL_PREFIX_RE.sub("", clean).strip()
    if not clean or looks_untranslated_text(clean):
        return ""
    if clean[0].islower():
        clean = clean[0].upper() + clean[1:]
    return clean.rstrip(".") + "."


def looks_untranslated_text(value: str) -> bool:
    latin_count = len(LATIN_CHAR_RE.findall(value or ""))
    cyrillic_count = len(CYRILLIC_CHAR_RE.findall(value or ""))
    return latin_count >= 12 and cyrillic_count == 0


def facts_sentence_from_items(values: list[str]) -> str:
    facts = []
    for value in values:
        clean = normalize_analysis_sentence(value, limit=80)
        if not clean or looks_untranslated_text(clean):
            continue
        facts.append(clean.rstrip("."))

    if not facts:
        return ""

    price_facts = [fact[5:].strip() for fact in facts if fact.lower().startswith("цена ")]
    if len(price_facts) == 1 and len(facts) == 1:
        return f"Цена в этой истории уже дошла до {price_facts[0]}."
    if len(price_facts) >= 2 and len(price_facts) == len(facts):
        return f"По цене уже фигурируют {price_facts[0]} и {price_facts[1]}."
    if len(facts) == 1:
        return f"Среди подтвержденных деталей уже есть {facts[0]}."
    return f"Среди подтвержденных деталей уже есть {facts[0]} и {facts[1]}."


def build_generic_summary_paragraph(item: CandidateItem, analysis: NewsAnalysis) -> str:
    subject = headline_subject(analysis.subject)
    if analysis.price_line:
        return f"{subject} оказался в центре новости из-за новой цены {analysis.price_line}."
    if analysis.specs:
        return f"{subject} получил заметное обновление, и главное здесь уже видно по характеристикам."
    if item.topic == "technology":
        return f"Вокруг {subject} появился новый ход со стороны компании, и его уже обсуждает tech-рынок."
    if item.topic == "gadgets":
        return f"Вокруг {subject} появился новый шаг со стороны бренда, и это уже может повлиять на выбор пользователей."
    return "В технологической ленте появилась новая история, за которой теперь будут внимательно следить."


def build_generic_importance_paragraph(item: CandidateItem, analysis: NewsAnalysis) -> str:
    if analysis.price_line:
        return "Такой ход сразу влияет на восприятие цены и на то, как бренд держит свою планку."
    if analysis.specs:
        return "По этим деталям уже можно понять, на кого рассчитан продукт и чем он будет брать пользователя."
    if item.topic == "technology":
        return "Такие решения обычно быстро меняют расклад для сервисов, рынка и обычных пользователей."
    if item.topic == "gadgets":
        return "Для покупателей это сигнал, что рынок снова меняет ожидания по устройствам и их возможностям."
    return "Эта история может быстро разойтись дальше, если за ней появятся новые подтверждения."


def compress_title_headline(title: str, max_words: int = 10) -> str:
    clean = neutralize_headline(title)
    if ";" in clean:
        first_clause = clean.split(";", 1)[0].strip(" ,.;:-")
        if 3 <= len(first_clause.split()) <= max_words:
            clean = first_clause
    words = clean.split()
    if len(words) <= max_words:
        return clean

    compact_words = [
        word for word in words
        if comparable_text_key(word) not in {"для", "с", "и", "на", "по", "в", "the", "a", "an"}
    ]
    if 4 <= len(compact_words) <= max_words:
        return " ".join(compact_words)
    return fit_headline_to_limit(clean, max_words=max_words)


def build_fact_driven_headline(analysis: NewsAnalysis) -> str:
    subject = headline_subject(analysis.subject)
    if analysis.price_line:
        candidate = fit_headline_to_limit(f"{subject} за {analysis.price_line}", max_words=10)
        if headline_is_usable(candidate, analysis.title_text):
            return candidate

    if analysis.specs:
        fragment = spec_to_headline_fragment(analysis.specs[0])
        if fragment:
            candidate = fit_headline_to_limit(f"{subject}: {fragment}", max_words=10)
            if headline_is_usable(candidate, analysis.title_text):
                return candidate

    return ""


def build_impact_headline(analysis: NewsAnalysis) -> str:
    haystack = " ".join(
        part for part in [analysis.title_text, analysis.core, analysis.interesting, analysis.takeaway, *analysis.story_points]
        if part
    ).lower()

    if any(keyword in haystack for keyword in ("terms of service", "условия использования", "copilot")) and any(
        keyword in haystack for keyword in ("trust", "не довер", "развлекательных целей", "entertainment purposes")
    ):
        return "Microsoft просит не доверять Copilot вслепую"

    if any(keyword in haystack for keyword in ("physical ai", "физический ии", "robot", "robotics", "робот")):
        if "япони" in haystack:
            return "Япония выводит физический AI в реальный бизнес"
        return "Физический AI выходит в реальный бизнес"

    if any(keyword in haystack for keyword in ("suno", "copyright", "ai music", "covers")):
        return "Suno открыла дверь для AI-каверов"

    if all(keyword in haystack for keyword in ("openai",)) and any(
        keyword in haystack for keyword in ("brockman", "брокман")
    ) and any(
        keyword in haystack for keyword in ("medical leave", "leave", "отпуск", "по болезни")
    ):
        return "Грег Брокман берет продукт OpenAI на себя"

    if any(keyword in haystack for keyword in ("sony", "ps5", "playstation")) and analysis.price_line:
        return fit_headline_to_limit(f"Sony подняла цену PS5 до {analysis.price_line}", max_words=10)

    subject = headline_subject(analysis.subject)
    candidate_source = first_non_generic_text(analysis.interesting, analysis.takeaway, analysis.core)
    candidate = sentence_to_headline(candidate_source, subject)
    if candidate:
        return candidate
    return ""


def headline_subject(value: str) -> str:
    clean = (value or "").strip()
    if not clean:
        return "Устройство"
    return clean[0].upper() + clean[1:]


def spec_to_sentence_fragment(value: str) -> str:
    clean = normalize_analysis_sentence(value, limit=80)
    if not clean:
        return ""
    return clean[0].lower() + clean[1:] if clean else ""


def spec_to_headline_fragment(value: str) -> str:
    clean = normalize_analysis_sentence(value, limit=60)
    if not clean:
        return ""
    return clean.replace(": ", " ").replace(":", " ").strip()


def sentence_to_headline(value: str, subject: str, max_words: int = 10) -> str:
    clean = normalize_analysis_sentence(value, limit=90)
    if not clean:
        return ""
    clean = strip_leading_connector(clean)
    clean = re.sub(r"^(?:цена стартует с|цена начинается с)\s+", "", clean, flags=re.IGNORECASE)
    clean = clean.replace(": ", " ").replace(":", " ").strip()
    if (
        subject
        and not subject_is_generic_for_headline(subject)
        and comparable_text_key(subject) not in comparable_text_key(clean)
    ):
        clean = f"{subject} {clean[0].lower() + clean[1:]}" if clean else subject
    return fit_headline_to_limit(clean, max_words=max_words)


def subject_is_generic_for_headline(subject: str) -> bool:
    return comparable_text_key(subject) in GENERIC_HEADLINE_SUBJECTS


def first_non_generic_text(*values: str) -> str:
    for value in values:
        clean = normalize_analysis_sentence(value, limit=140)
        if not clean:
            continue
        if comparable_text_key(clean) in GENERIC_INTERESTING_KEYS:
            continue
        return clean
    return ""


def headline_is_usable(headline: str, title: str) -> bool:
    clean = neutralize_headline(headline or "")
    if not clean:
        return False
    words = clean.split()
    if not 2 <= len(words) <= 10:
        return False

    tokens = [word.lower().strip(" ,.;:!?") for word in words if word.strip(" ,.;:!?")]
    meaningful = [
        token for token in tokens
        if len(token) >= 2 or token in HEADLINE_SHORT_TOKEN_ALLOWLIST or any(character.isdigit() for character in token)
    ]
    if len(meaningful) < 2:
        return False
    if any(len(token) == 1 and token not in HEADLINE_SHORT_TOKEN_ALLOWLIST for token in tokens):
        return False
    if (
        shared_meaningful_tokens(title, clean) == 0
        and shared_prefix_tokens(title, clean) == 0
        and not any(character.isdigit() for character in clean)
    ):
        return False
    return True


def score_post_variant(
    title: str,
    headline: str,
    paragraphs: list[str],
    analysis: NewsAnalysis,
    strategy: str
) -> tuple[int, int, int]:
    full_text = " ".join([headline, *paragraphs]).lower()
    shared_tokens = shared_meaningful_tokens(title, headline)
    factual_headline = compress_title_headline(title)

    headline_score = 4
    if len(headline.split()) <= 10:
        headline_score += 2
    if shared_tokens >= 2:
        headline_score += 2
    elif shared_prefix_tokens(title, headline) >= 1:
        headline_score += 1
    if any(character.isdigit() for character in headline):
        headline_score += 1
    if analysis.subject.lower() in headline.lower():
        headline_score += 1
    if comparable_text_key(headline) != comparable_text_key(factual_headline):
        headline_score += 1

    curiosity_score = 4
    if 2 <= len(paragraphs) <= 3:
        curiosity_score += 2
    if analysis.numbers:
        curiosity_score += 2
    if len({comparable_text_key(paragraph) for paragraph in paragraphs}) == len(paragraphs):
        curiosity_score += 2

    emotion_score = 3
    if strategy != "factual":
        emotion_score += 2
    if strategy == "impact":
        emotion_score += 1
    if any(character.isdigit() for character in full_text):
        emotion_score += 1
    if analysis.takeaway:
        emotion_score += 2

    return (
        max(1, min(10, headline_score)),
        max(1, min(10, curiosity_score)),
        max(1, min(10, emotion_score))
    )


def shared_meaningful_tokens(title: str, headline: str) -> int:
    stopwords = {"для", "с", "и", "на", "по", "в", "the", "a", "an", "of"}
    title_tokens = {
        token.lower().strip(" ,.;:!?")
        for token in title.split()
        if token.lower().strip(" ,.;:!?") and token.lower().strip(" ,.;:!?") not in stopwords
    }
    headline_tokens = {
        token.lower().strip(" ,.;:!?")
        for token in headline.split()
        if token.lower().strip(" ,.;:!?") and token.lower().strip(" ,.;:!?") not in stopwords
    }
    return len(title_tokens & headline_tokens)


def shared_prefix_tokens(title: str, headline: str) -> int:
    title_tokens = [
        token.lower().strip(" ,.;:!?")
        for token in title.split()
        if len(token.lower().strip(" ,.;:!?")) >= 4
    ]
    headline_tokens = [
        token.lower().strip(" ,.;:!?")
        for token in headline.split()
        if len(token.lower().strip(" ,.;:!?")) >= 4
    ]
    matches = 0
    for left in title_tokens:
        if any(left[:4] == right[:4] for right in headline_tokens):
            matches += 1
    return matches


def build_spec_lines(item: CandidateItem, title: str, summary: str, max_lines: int) -> list[str]:
    if max_lines <= 0:
        return []

    model_specs = extract_model_spec_lines(item, title, summary, max_models=max_lines)
    if model_specs:
        return model_specs[:max_lines]

    return extract_spec_highlights(item, title, summary, max_specs=max_lines)


def normalize_story_sections(
    title: str,
    lead: str,
    story_bullets: list[str],
    fallback_story: list[str],
    max_bullets: int
) -> tuple[str, list[str]]:
    title_key = comparable_text_key(title)
    seen: set[str] = {title_key} if title_key else set()

    normalized_lead = lead.strip()
    lead_key = comparable_text_key(normalized_lead)
    if lead_key and lead_key in seen:
        normalized_lead = ""
    elif lead_key:
        seen.add(lead_key)

    cleaned_bullets: list[str] = []
    for bullet in story_bullets:
        clean = bullet.strip()
        if not clean:
            continue
        bullet_key = comparable_text_key(clean)
        if bullet_key in seen:
            continue
        seen.add(bullet_key)
        cleaned_bullets.append(clean)
        if len(cleaned_bullets) >= max_bullets:
            break

    if normalized_lead:
        return normalized_lead, cleaned_bullets

    for paragraph in fallback_story:
        clean = paragraph.strip()
        if not clean:
            continue
        paragraph_key = comparable_text_key(clean)
        if paragraph_key in seen:
            continue
        normalized_lead = truncate(clean, 190)
        seen.add(paragraph_key)
        break

    if normalized_lead:
        return normalized_lead, cleaned_bullets

    if cleaned_bullets:
        return cleaned_bullets[0], cleaned_bullets[1:]

    return "Новый материал по теме гаджетов или технологий уже появился в ленте канала.", []


def build_price_lines(item: CandidateItem, title: str, summary: str, max_lines: int) -> list[str]:
    if max_lines <= 0:
        return []

    price_block = build_price_block(item, title, summary, max_lines=max_lines)
    if not price_block:
        return []

    if len(price_block) == 1:
        plain_price = extract_price_value(f"{title}. {summary}")
        return [plain_price] if plain_price else []

    return price_block[1:1 + max_lines]


def build_takeaway_line(
    item: CandidateItem,
    title: str,
    summary: str,
    has_specs: bool,
    has_price: bool
) -> str:
    haystack = f"{title} {summary}".lower()

    if item.topic == "recalls":
        return "Пользователям стоит проверить, касается ли новость их устройства или сервиса."
    if item.topic == "law":
        return "Это может повлиять на правила использования сервиса, платформы или устройства."
    if item.topic == "new_models":
        if has_specs and has_price:
            return "По характеристикам и цене уже можно понять позиционирование новинки."
        if has_specs:
            return "Материал даёт первые технические ориентиры по новому устройству."
        return "Это ранний сигнал о том, куда бренд двигает продуктовую линейку."
    if item.topic == "prices":
        return "Новость помогает понять новое ценовое позиционирование устройства или бренда."
    if item.topic == "electric":
        if has_specs:
            return "Для гаджетов особенно важны батарея, производительность и скорость зарядки."
        return "Это влияет на то, насколько устройство будет практичным в повседневном использовании."
    if item.topic in {"gadgets", "technology"}:
        if any(keyword in haystack for keyword in ("smartphone", "iphone", "android", "laptop", "earbuds", "смартфон", "ноутбук", "наушники")):
            return "Такие обновления напрямую влияют на повседневный цифровой опыт пользователя."
        return "Это показывает, какие технологии быстрее всего доходят до массовых устройств и сервисов."
    if item.topic == "production":
        return "Подобные новости обычно отражают изменения в поставках, локализации и стратегии бренда."
    if item.topic == "sales":
        return "Это полезный индикатор спроса и текущего состояния tech-рынка."
    if item.topic == "tips":
        return "Материал можно использовать как практическую подсказку по использованию технологии."
    if item.topic == "accidents":
        return "Новость важна как сигнал по продуктовым рискам и безопасности."

    return ""


def build_source_meta_line(item: CandidateItem) -> str:
    return f"🕒 {escape_text(format_russian_date(item.published_at_utc))} • {escape_text(source_label(item))}"


def build_read_more_line(item: CandidateItem) -> str:
    label = truncate(item.source_name, 36)
    return f"🔗 <a href=\"{escape_attr(item.url)}\">Читать в {escape_text(label)}</a>"


def build_original_spoiler(item: CandidateItem, title: str) -> str:
    original_title = neutralize_headline(item.original_title or "")
    if not original_title:
        return ""
    if comparable_text_key(original_title) == comparable_text_key(title):
        return ""
    return f"<tg-spoiler>Оригинальный заголовок: {escape_text(original_title)}</tg-spoiler>"


def comparable_text_key(text: str) -> str:
    return EXTRA_SPACE_RE.sub(" ", (text or "").lower()).strip(" .")


def build_reference_paragraphs(item: CandidateItem, title: str, summary: str, max_paragraphs: int) -> list[str]:
    paragraphs: list[str] = []
    model_specs = extract_model_spec_lines(item, title, summary, max_models=2)
    specs = [] if model_specs else extract_spec_highlights(item, title, summary, max_specs=3)

    if model_specs:
        paragraphs.extend(model_specs[:2])
    elif specs:
        paragraphs.append(", ".join(specs[:3]))

    if summary:
        paragraphs.extend(group_story_sentences(summary, max_paragraphs=max_paragraphs))

    unique: list[str] = []
    seen: set[str] = set()
    title_key = title.lower().strip(" .")
    for paragraph in paragraphs:
        clean = paragraph.strip()
        if not clean:
            continue
        if clean.lower().strip(" .") == title_key:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(clean)
        if len(unique) >= max_paragraphs:
            break

    if not unique:
        unique.append("Новый материал по теме гаджетов или технологий уже появился в ленте канала.")

    return unique


def group_story_sentences(summary: str, max_paragraphs: int) -> list[str]:
    paragraphs: list[str] = []
    raw_paragraphs = [part.strip() for part in re.split(r"\n{2,}", summary) if part.strip()]
    if not raw_paragraphs:
        raw_paragraphs = [summary]

    for raw_paragraph in raw_paragraphs:
        sentences = [neutralize_text(part) for part in SUMMARY_SPLIT_RE.split(raw_paragraph) if part.strip()]
        if not sentences:
            continue

        current: list[str] = []
        for sentence in sentences:
            if current and (len(" ".join(current + [sentence])) > 220 or len(current) >= 2):
                paragraphs.append(" ".join(current))
                current = [sentence]
            else:
                current.append(sentence)
            if len(paragraphs) >= max_paragraphs:
                break

        if current and len(paragraphs) < max_paragraphs:
            paragraphs.append(" ".join(current))
        if len(paragraphs) >= max_paragraphs:
            break

    return paragraphs[:max_paragraphs]


def emphasize_paragraph(text: str) -> str:
    escaped = escape_text(text)
    escaped = PRICE_VALUE_RE.sub(r"<b>\1</b>", escaped)
    for phrase in (
        "быстрая зарядка",
        "мультимедиа",
        "экосистема",
        "ai",
        "искусственный интеллект",
        "чип",
        "процессор",
        "нейросеть",
    ):
        escaped = re.sub(
            rf"\b({re.escape(phrase)})\b",
            r"<b>\1</b>",
            escaped,
            flags=re.IGNORECASE
        )
    return escaped


def build_channel_cta(channel_id: str) -> str:
    if not channel_id.startswith("@"):
        return ""
    handle = channel_id.lstrip("@")
    return f"👉 <a href=\"https://t.me/{escape_attr(handle)}\">{escape_text(channel_id)}. Подписаться</a>"


def build_story_blocks(summary: str, max_bullets: int, skip_model_sentences: bool = False) -> tuple[str, list[str]]:
    if not summary:
        return "", []

    sentences = [neutralize_text(part) for part in SENTENCE_SPLIT_RE.split(summary) if part.strip()]
    if not sentences:
        clean_summary = neutralize_text(summary)
        return clean_summary, []

    lead = truncate(sentences[0], 190)
    if skip_model_sentences and sentence_is_model_heavy(sentences[0]):
        lead = ""
    bullets: list[str] = []

    for sentence in sentences[1:]:
        if skip_model_sentences and (
            sentence_is_model_heavy(sentence) or extract_specs_from_text(sentence, max_specs=1)
        ):
            continue
        if extract_price_value(sentence):
            continue
        bullet = truncate(strip_leading_connector(sentence), 140)
        if bullet and bullet.lower() != lead.lower():
            bullets.append(bullet)
        if len(bullets) >= max_bullets:
            break

    if not bullets and len(sentences) == 1 and len(lead) > 170:
        shortened = truncate(lead, 120)
        if shortened != lead:
            bullets.append(lead[len(shortened):].strip(" .,;:-"))
            lead = shortened

    return lead, [bullet for bullet in bullets if bullet]


def extract_model_spec_lines(item: CandidateItem, title: str, summary: str, max_models: int) -> list[str]:
    if max_models <= 0 or not should_include_specs(item, title, summary):
        return []

    text = EXTRA_SPACE_RE.sub(" ", summary or title).strip()
    mentions = extract_model_mentions(text)
    if len(mentions) < 2:
        return []

    grouped: dict[str, list[str]] = {}
    ordered_models: list[str] = []

    for index, (model_name, start, end) in enumerate(mentions):
        segment_end = mentions[index + 1][1] if index + 1 < len(mentions) else len(text)
        segment = text[start:segment_end]
        specs = extract_specs_from_text(segment, max_specs=3)
        if not specs:
            continue
        if model_name not in grouped:
            grouped[model_name] = []
            ordered_models.append(model_name)
        for spec in specs:
            if spec not in grouped[model_name]:
                grouped[model_name].append(spec)

    lines = [
        f"{model_name}: {', '.join(grouped[model_name][:3])}"
        for model_name in ordered_models
        if grouped.get(model_name)
    ]
    if len(lines) < 2:
        return []
    return lines[:max_models]


def extract_spec_highlights(item: CandidateItem, title: str, summary: str, max_specs: int) -> list[str]:
    if max_specs <= 0 or not should_include_specs(item, title, summary):
        return []

    text = EXTRA_SPACE_RE.sub(" ", f"{title}. {summary}").strip()
    if not text:
        return []

    return extract_specs_from_text(text, max_specs=max_specs)


def should_include_specs(item: CandidateItem, title: str, summary: str) -> bool:
    haystack = f"{title} {summary}".lower()

    if item.topic in SPEC_FOCUS_TOPICS:
        return True

    if item.topic == "technology" and any(keyword in haystack for keyword in GADGET_KEYWORDS):
        return True

    has_model_hint = any(keyword in haystack for keyword in MODEL_KEYWORDS)
    has_gadget_hint = any(keyword in haystack for keyword in GADGET_KEYWORDS)
    has_spec_hint = any(keyword in haystack for keyword in ("характерист", "spec", "техданн"))
    return has_spec_hint and (has_model_hint or has_gadget_hint)


def extract_specs_from_text(text: str, max_specs: int) -> list[str]:
    extractors = (
        extract_power_spec,
        extract_battery_spec,
        extract_range_spec,
        extract_acceleration_spec,
        extract_charging_spec,
        extract_torque_spec,
        extract_engine_spec,
        extract_voltage_spec,
        extract_screen_spec,
        extract_memory_spec,
        extract_camera_spec
    )

    specs: list[str] = []
    seen: set[str] = set()

    for extractor in extractors:
        spec = extractor(text)
        if not spec:
            continue
        key = spec.lower()
        if key in seen:
            continue
        seen.add(key)
        specs.append(spec)
        if len(specs) >= max_specs:
            break

    return specs


def extract_model_mentions(text: str) -> list[tuple[str, int, int]]:
    mentions: list[tuple[str, int, int]] = []
    seen: set[str] = set()

    for match in MODEL_MENTION_RE.finditer(text):
        brand = match.group("brand").strip()
        tail_tokens = [clean_token(token) for token in match.group("tail").split()]
        model_tokens: list[str] = []

        for token in tail_tokens:
            if not is_model_token(token):
                break
            model_tokens.append(token)

        if not model_tokens:
            continue

        model_name = " ".join([brand] + model_tokens)
        key = model_name.lower()
        if key in seen:
            continue
        seen.add(key)
        mentions.append((model_name, match.start(), match.end()))

    return mentions


def is_model_token(token: str) -> bool:
    cleaned = clean_token(token)
    if not cleaned:
        return False
    if cleaned.lower() in MODEL_STOPWORDS:
        return False
    if any(char.isdigit() for char in cleaned):
        return True
    if cleaned != cleaned.lower():
        return True
    return False


def clean_token(token: str) -> str:
    return token.strip(" ,.;:()[]{}<>\"'")


def sentence_is_model_heavy(text: str) -> bool:
    cleaned = strip_leading_connector(text)
    return bool(
        len(extract_model_mentions(cleaned)) >= 2
        or (
            extract_model_mentions(cleaned)
            and (extract_specs_from_text(cleaned, max_specs=1) or extract_price_value(cleaned))
        )
    )


def strip_leading_connector(text: str) -> str:
    return re.sub(r"^(?:и|а|но|also|and)\s+", "", text.strip(), flags=re.IGNORECASE)


def build_price_block(item: CandidateItem, title: str, summary: str, max_lines: int) -> list[str]:
    text = EXTRA_SPACE_RE.sub(" ", f"{title}. {summary}").strip()
    if not text:
        return []

    model_prices = extract_model_price_lines(item, title, summary, max_lines=max_lines)
    if len(model_prices) > 1:
        return ["💰 <b>Цены:</b>", *model_prices[:max_lines]]

    if model_prices:
        return [f"💰 <b>Цена:</b> {model_prices[0].split(': ', 1)[-1]}"]

    price_value = extract_price_value(text)
    if not price_value:
        return []
    return [f"💰 <b>Цена:</b> {price_value}"]


def extract_model_price_lines(item: CandidateItem, title: str, summary: str, max_lines: int) -> list[str]:
    if max_lines <= 0 or not should_include_specs(item, title, summary):
        return []

    text = EXTRA_SPACE_RE.sub(" ", summary or title).strip()
    mentions = extract_model_mentions(text)
    if len(mentions) < 2:
        return []

    lines: list[str] = []
    for index, (model_name, start, end) in enumerate(mentions):
        segment_end = mentions[index + 1][1] if index + 1 < len(mentions) else len(text)
        segment = text[start:segment_end]
        price_value = extract_price_value(segment)
        if not price_value:
            continue
        lines.append(f"{model_name}: {price_value}")
        if len(lines) >= max_lines:
            break
    return lines


def extract_price_value(text: str) -> str | None:
    for pattern in PRICE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        value = EXTRA_SPACE_RE.sub(" ", match.group("value")).strip(" .,:;")
        lowered = value.lower()
        if lowered.startswith("from "):
            value = f"от {value[5:]}"
        value = re.sub(r"\beuros?\b", "евро", value, flags=re.IGNORECASE)
        value = re.sub(r"\beur\b", "евро", value, flags=re.IGNORECASE)
        value = re.sub(r"\b(?:us|u\.s\.)\s+dollars?\b", "долларов", value, flags=re.IGNORECASE)
        value = re.sub(r"\baustralian dollars?\b", "австралийских долларов", value, flags=re.IGNORECASE)
        value = re.sub(r"\bcanadian dollars?\b", "канадских долларов", value, flags=re.IGNORECASE)
        value = re.sub(r"\bsingapore dollars?\b", "сингапурских долларов", value, flags=re.IGNORECASE)
        value = re.sub(r"\bdollars?\b", "долларов", value, flags=re.IGNORECASE)
        value = re.sub(r"\bpounds?\b", "фунтов", value, flags=re.IGNORECASE)
        return value
    return None


def extract_power_spec(text: str) -> str | None:
    for match in POWER_RE.finditer(text):
        unit = normalize_unit(match.group("unit"))
        context = context_window(text, match.start(), match.end())

        if unit == "кВт" and not re.search(r"мощност|power|output|двигател|motor|силов", context, re.IGNORECASE):
            continue
        if unit == "кВт" and re.search(r"заряд|charging|battery|батар", context, re.IGNORECASE):
            continue

        return f"Мощность: {normalize_number(match.group('value'))} {unit}"
    return None


def extract_battery_spec(text: str) -> str | None:
    match = BATTERY_RE.search(text)
    if not match:
        return None
    return f"Батарея: {normalize_number(match.group('value'))} кВт·ч"


def extract_range_spec(text: str) -> str | None:
    for pattern in RANGE_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"Запас хода: {normalize_number(match.group('value'))} км"
    return None


def extract_acceleration_spec(text: str) -> str | None:
    match = ACCELERATION_RE.search(text)
    if not match:
        return None
    return f"Разгон 0-100 км/ч: {normalize_number(match.group('value'))} с"


def extract_charging_spec(text: str) -> str | None:
    for pattern in CHARGING_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"Быстрая зарядка: до {normalize_number(match.group('value'))} кВт"
    return None


def extract_torque_spec(text: str) -> str | None:
    match = TORQUE_RE.search(text)
    if not match:
        return None
    return f"Крутящий момент: {normalize_number(match.group('value'))} Нм"


def extract_engine_spec(text: str) -> str | None:
    for pattern in ENGINE_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"Двигатель: {normalize_number(match.group('value'))} л"
    return None


def extract_voltage_spec(text: str) -> str | None:
    for pattern in VOLTAGE_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"Архитектура: {normalize_number(match.group('value'))} В"
    return None


def extract_screen_spec(text: str) -> str | None:
    for pattern in SCREEN_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"Экран: {normalize_number(match.group('value'))} дюйма"
    return None


def extract_memory_spec(text: str) -> str | None:
    for pattern in MEMORY_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"Память: {normalize_number(match.group('value'))} {normalize_unit(match.group('unit'))}"
    return None


def extract_camera_spec(text: str) -> str | None:
    for pattern in CAMERA_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"Камера: {normalize_number(match.group('value'))} Мп"
    return None


def context_window(text: str, start: int, end: int, padding: int = 28) -> str:
    left = max(0, start - padding)
    right = min(len(text), end + padding)
    return text[left:right]


def normalize_number(value: str) -> str:
    return value.strip().replace(".", ",")


def normalize_unit(value: str) -> str:
    lowered = value.strip().lower().replace(" ", "")
    mapping = {
        "л.с.": "л.с.",
        "л.с": "л.с.",
        "лс": "л.с.",
        "hp": "л.с.",
        "bhp": "л.с.",
        "kw": "кВт",
        "квт": "кВт",
        "gb": "ГБ",
        "гб": "ГБ",
        "tb": "ТБ",
        "тб": "ТБ"
    }
    return mapping.get(lowered, value.strip())


def build_hashtags(item: CandidateItem, title: str) -> list[str]:
    title_haystack = f"{title} {item.title}".lower()
    summary_haystack = f"{item.summary} {item.source_name}".lower()
    haystack = f"{title_haystack} {summary_haystack}"
    tags: list[str] = []

    if item.source_kind == "insider" or "ИНСАЙД" in (item.post_label or "").upper():
        append_hashtag(tags, "Инсайд")
    elif item.source_kind in {"media", "official"} or "НОВОСТЬ" in (item.post_label or "").upper():
        append_hashtag(tags, "Новость")

    for tag in detect_gadget_hashtags(title_haystack, max_tags=3):
        append_hashtag(tags, tag)

    model_tag = extract_model_hashtag(f"{title}. {item.summary}")
    if model_tag:
        append_hashtag(tags, model_tag)

    for phrase, tag in BRAND_TAGS:
        if phrase_in_text(title_haystack, phrase) and tag not in tags:
            append_hashtag(tags, tag)
        if len(tags) >= 3:
            break

    for phrase, tag in BRAND_TAGS:
        if phrase_in_text(summary_haystack, phrase) and tag not in tags:
            append_hashtag(tags, tag)
        if len(tags) >= 4:
            break

    for tag in detect_gadget_hashtags(haystack, max_tags=4):
        append_hashtag(tags, tag)

    for tag in topic_hashtag_candidates(item.topic):
        append_hashtag(tags, tag)

    for base_tag in ("Технологии", "Гаджеты", "TechNews"):
        append_hashtag(tags, base_tag)

    while len(tags) < 4:
        append_hashtag(tags, "Технологии")

    return tags[:6]


def extract_model_hashtag(text: str) -> str:
    mentions = extract_model_mentions(text)
    if not mentions:
        return ""
    model_name = mentions[0][0]
    model_parts = [part for part in model_name.split() if part]
    if len(model_parts) >= 2:
        if model_parts[-1].isdigit():
            return ""
        product_tag = sanitize_hashtag(model_parts[-1])
        if product_tag:
            return product_tag
    return sanitize_hashtag(model_name)


def detect_gadget_hashtags(haystack: str, max_tags: int) -> list[str]:
    tags: list[str] = []
    for keyword, tag in GADGET_HASHTAG_RULES:
        if phrase_in_text(haystack, keyword) and tag not in tags:
            tags.append(tag)
        if len(tags) >= max_tags:
            break
    return tags


def phrase_in_text(haystack: str, phrase: str) -> bool:
    if not phrase:
        return False
    if not re.search(r"[0-9A-Za-zА-Яа-яЁё]", phrase):
        return phrase in haystack

    pattern = rf"(?<![0-9A-Za-zА-Яа-яЁё]){re.escape(phrase)}(?![0-9A-Za-zА-Яа-яЁё])"
    return re.search(pattern, haystack) is not None


def sanitize_hashtag(value: str, max_length: int = 32) -> str:
    cleaned = HASHTAG_CLEAN_RE.sub("", value)
    cleaned = cleaned[:max_length]
    if not cleaned:
        return ""
    if not any(char.isalpha() for char in cleaned):
        return ""
    return cleaned


def append_hashtag(tags: list[str], value: str) -> None:
    tag = sanitize_hashtag(value)
    if not tag or tag in tags:
        return
    tags.append(tag)


def topic_hashtag_candidates(topic: str) -> list[str]:
    topic_tag = TOPIC_HASHTAGS.get(topic, "Технологии")
    if topic == "gadgets":
        return [topic_tag]
    if topic == "technology":
        return ["AI", topic_tag]
    if topic == "industry":
        return ["Индустрия"]
    return [topic_tag]


def render_hashtags(tags: list[str]) -> str:
    return " ".join(f"#{escape_text(tag)}" for tag in tags if tag)


def detect_brand_label(item: CandidateItem, title: str = "") -> str:
    title_haystack = f"{title} {item.title}".lower()
    summary_haystack = f"{item.summary} {item.source_name}".lower()

    for phrase, tag in BRAND_TAGS:
        if phrase_in_text(title_haystack, phrase):
            return tag

    for phrase, tag in BRAND_TAGS:
        if phrase_in_text(summary_haystack, phrase):
            return tag

    source_tag = SOURCE_TAGS.get(item.source_group)
    if source_tag:
        return source_tag

    return item.source_name.split()[0]


def source_label(item: CandidateItem) -> str:
    host = urlsplit(item.url).netloc.lower().lstrip("www.")
    if host:
        return f"{item.source_name} • {host}"
    return item.source_name


def escape_text(value: str) -> str:
    return html.escape(value, quote=False)


def escape_attr(value: str) -> str:
    return html.escape(value, quote=True)


def neutralize_headline(text: str) -> str:
    cleaned = neutralize_text(text)
    return cleaned.rstrip(".")


def neutralize_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = SUMMARY_ARTIFACT_RE.sub(" ", cleaned)
    cleaned = EMPTY_PARENS_RE.sub(" ", cleaned)
    for target, replacement in CLICKBAIT_REPLACEMENTS:
        cleaned = re.sub(rf"\b{re.escape(target)}\b", replacement, cleaned, flags=re.IGNORECASE)

    cleaned = MULTI_PUNCTUATION_RE.sub(".", cleaned)
    cleaned = cleaned.replace("« ", "«").replace(" »", "»")
    cleaned = EXTRA_SPACE_RE.sub(" ", cleaned).strip(" -–—.,")

    if not cleaned:
        return "Новость о технологиях"

    return cleaned[0].upper() + cleaned[1:]


def build_headline(item: CandidateItem, title: str, config: AppConfig) -> str:
    post_label = resolve_post_label(item, config)
    if post_label:
        return f"<b>{escape_text(post_label)}: {escape_text(title)}</b>"
    emoji = TOPIC_EMOJIS.get(item.topic, "")
    if emoji:
        return f"<b>{escape_text(emoji)} {escape_text(title)}</b>"
    return f"<b>{escape_text(title)}</b>"


def resolve_post_label(item: CandidateItem, config: AppConfig) -> str:
    current_label = (item.post_label or "").upper()
    if item.source_kind == "insider" or "ИНСАЙД" in current_label:
        return config.editorial.insider_label or item.post_label
    if item.source_kind in {"media", "official"} or "НОВОСТЬ" in current_label:
        return config.editorial.news_label or item.post_label
    return item.post_label


def render_persona_comments(item: CandidateItem, config: AppConfig) -> list[str]:
    if not config.editorial.persona_comments_enabled or not item.persona_comment:
        return []

    clean = item.persona_comment.strip()
    if not clean:
        return []
    persona_name = item.persona_name or "Комментарий"
    return [f"<blockquote><b>{escape_text(persona_name)}</b>\n{escape_text(clean)}</blockquote>"]


def render_tehnio_persona(item: CandidateItem) -> list[str]:
    if not item.persona_comment:
        return []

    persona_labels = {
        "Архимед Сиракузский": "Архимед",
        "Диоген Синопский": "Диоген",
        "Геродот": "Геродот",
    }
    persona_name = persona_labels.get(item.persona_name, item.persona_name or "Комментарий")
    comment = strip_wrapping_quotes(item.persona_comment.strip())
    if not comment:
        return []
    return [
        f"💬 <b>{escape_text(persona_name)}:</b>",
        f"«{escape_text(comment)}»",
    ]


def build_story_link(url: str, config: AppConfig) -> str:
    return f"<a href=\"{escape_attr(url)}\">{escape_text(config.editorial.link_text)}</a>"


def build_subscribe_cta(config: AppConfig) -> str:
    cta_text = (config.editorial.subscribe_cta_text or "").strip()
    channel_id = (config.telegram.channel_id or "").strip()
    if not cta_text:
        return ""
    if channel_id.startswith("@"):
        handle = channel_id.lstrip("@")
        return f"<a href=\"https://t.me/{escape_attr(handle)}\">{escape_text(cta_text)}</a>"
    return escape_text(cta_text)


def build_tehnio_headline(item: CandidateItem, analysis: NewsAnalysis, fallback_headline: str) -> str:
    heuristic_headline = build_tehnio_fallback_headline(item, analysis)
    candidates = [item.generated_headline, heuristic_headline, fallback_headline, compress_title_headline(item.title), item.title]
    for value in candidates:
        raw = (value or "").strip()
        if not raw:
            continue
        clean = fit_headline_to_limit(neutralize_headline(raw), max_words=12)
        if clean and not looks_untranslated_text(clean):
            return clean
    return heuristic_headline or "Новая история в мире технологий"


def build_tehnio_fallback_headline(item: CandidateItem, analysis: NewsAnalysis) -> str:
    haystack = f"{item.title} {item.summary}".lower()
    brand = detect_tehnio_primary_brand(item)
    subject = shorten_subject(analysis.subject or "")
    generic_subjects = {comparable_text_key(value) for value in GENERIC_HEADLINE_SUBJECTS}
    subject_key = comparable_text_key(subject)
    brand_key = comparable_text_key(brand)

    if "android xr" in haystack and "vision pro" in haystack:
        if brand:
            return f"{brand} готовит ответ Vision Pro — Android XR"
        return "Android XR готовят как ответ Vision Pro"
    if "android xr" in haystack:
        if brand:
            return f"{brand} развивает платформу Android XR"
        return "Android XR выходит в центр новой гонки"
    if "gemini" in haystack and brand:
        return f"{brand} делает ставку на устройства с Gemini"
    if brand and subject and subject_key not in generic_subjects and subject_key != brand_key:
        return f"{brand} раскрыла детали о {subject}"
    if brand:
        return f"{brand} снова в центре tech-повестки"
    return "Технологическая новость дня"


def build_tehnio_intro_paragraphs(item: CandidateItem, analysis: NewsAnalysis, compact: bool) -> list[str]:
    if item.generated_intro:
        intro = normalize_tehnio_intro_text(item.generated_intro, limit=260 if compact else 360)
        return [intro] if intro else []

    heuristic_intro = build_tehnio_intro_heuristic(item)
    if heuristic_intro:
        intro = normalize_tehnio_intro_text(heuristic_intro, limit=260 if compact else 360)
        if intro:
            return [intro]

    sentences: list[str] = []
    seen: set[str] = set()
    candidates = [
        analysis.core,
        first_distinct_sentence(analysis.story_points, exclude=[item.title, analysis.core]),
        analysis.interesting,
        analysis.takeaway,
        build_generic_summary_paragraph(item, analysis),
    ]

    for candidate in candidates:
        clean = normalize_tehnio_intro_sentence(candidate, limit=145 if compact else 180)
        if not clean:
            continue
        key = comparable_text_key(clean)
        if key in seen or key == comparable_text_key(item.title):
            continue
        seen.add(key)
        sentences.append(clean)
        if len(sentences) >= (2 if compact else 2):
            break

    if len(sentences) < 2:
        for candidate in split_story_sentences(item.summary or "", max_items=6):
            clean = normalize_tehnio_intro_sentence(candidate, limit=145 if compact else 180)
            if not clean:
                continue
            key = comparable_text_key(clean)
            if key in seen or key == comparable_text_key(item.title):
                continue
            seen.add(key)
            sentences.append(clean)
            if len(sentences) >= 2:
                break

    if not sentences:
        fallback = normalize_tehnio_intro_text(build_generic_summary_paragraph(item, analysis), limit=170)
        return [fallback] if fallback else []

    intro = " ".join(sentence.rstrip(".") + "." for sentence in sentences).strip()
    return [intro]


def build_tehnio_fact_lines(item: CandidateItem, analysis: NewsAnalysis, max_items: int) -> list[str]:
    if item.generated_facts:
        facts = [normalize_fact_candidate(value, limit=96) for value in item.generated_facts]
        return [fact for fact in facts if fact][:max_items]

    candidates: list[str] = []
    seen: set[str] = set()
    haystack = f"{item.title} {item.summary}".lower()

    for value in analysis.specs + analysis.numbers:
        clean = normalize_fact_candidate(value, limit=96)
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            candidates.append(clean)
        if len(candidates) >= max_items:
            return candidates

    for sentence in split_story_sentences(item.summary or "", max_items=8):
        clean = normalize_fact_candidate(sentence, limit=96)
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        candidates.append(clean)
        if len(candidates) >= max_items:
            return candidates

    if "gemini" in haystack and "gemini ai" not in seen:
        candidates.append("ожидается интеграция с Gemini AI")
    if "android xr" in haystack and all("android xr" not in item.lower() for item in candidates):
        candidates.insert(0, "новая платформа Android XR")

    return candidates[:max_items]


def normalize_tehnio_intro_text(value: str, limit: int) -> str:
    clean = normalize_body_paragraph(value, limit=limit)
    if not clean or looks_untranslated_text(clean):
        return ""
    return clean


def normalize_tehnio_intro_sentence(value: str, limit: int) -> str:
    clean = normalize_analysis_sentence(value, limit=limit)
    if not clean or looks_untranslated_text(clean):
        return ""
    if comparable_text_key(clean) in GENERIC_TAKEAWAY_KEYS or comparable_text_key(clean) in GENERIC_INTERESTING_KEYS:
        return ""
    clean = strip_leading_connector(clean)
    clean = re.sub(
        r"^(?:по сути|коротко|что важно|это значит,? что|это показывает,? что|это говорит о том,? что)\s*",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip(" ,.")
    if len(clean.split()) < 4:
        return ""
    if clean[0].islower():
        clean = clean[0].upper() + clean[1:]
    return clean.rstrip(".") + "."


def build_tehnio_intro_heuristic(item: CandidateItem) -> str:
    haystack = f"{item.title} {item.summary}".lower()
    brand = detect_tehnio_primary_brand(item)
    if not brand:
        return ""

    if "android xr" in haystack and "vision pro" in haystack:
        tail = ""
        if any(marker in haystack for marker in ("lighter", "cheaper", "доступ", "легк")):
            tail = " Ставка делается на более лёгкие и доступные гарнитуры для массового рынка."
        elif "gemini" in haystack:
            tail = " Одной из ключевых функций платформы может стать интеграция Gemini AI."
        return f"{brand} вместе с партнёрами развивает Android XR как ответ Apple Vision Pro.{tail}".strip()

    if "gemini" in haystack and "android" in haystack:
        return f"{brand} усиливает Android-экосистему за счёт более тесной интеграции с Gemini AI."

    return ""


def normalize_fact_candidate(value: str, limit: int = 96) -> str:
    clean = normalize_complete_fact(value, limit=limit)
    if not clean or looks_untranslated_text(clean):
        return ""
    clean = strip_leading_connector(clean)
    clean = clean.rstrip(".")
    clean = re.sub(r"^(?:среди подтвержденных деталей уже есть|в центре новости оказалась|коротко,?\s*)", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^(партн(?:е|ё)ры),\s+", r"\1: ", clean, flags=re.IGNORECASE)
    clean = clean.strip(" ,.")
    if not clean:
        return ""
    if clean[0].isupper():
        clean = clean[0].lower() + clean[1:]
    return clean


def normalize_complete_fact(value: str, limit: int) -> str:
    raw = normalize_analysis_sentence(value, limit=max(limit * 2, 140))
    if not raw:
        return ""
    raw = raw.rstrip(".")
    for separator in ("; ", " — ", " – ", ". ", ", but ", ", and ", ", но ", ", а ", ", чтобы ", ", because "):
        head = raw.split(separator, 1)[0].strip()
        if 16 <= len(head) <= limit:
            raw = head
            break

    if len(raw) > limit:
        return ""
    if raw.endswith("..."):
        return ""
    if fact_looks_unfinished(raw):
        return ""
    return raw


def fact_looks_unfinished(value: str) -> bool:
    clean = normalize_analysis_sentence(value, limit=200).lower().rstrip(".!?")
    if not clean:
        return True
    trailing_words = {
        "и",
        "а",
        "но",
        "или",
        "чтобы",
        "который",
        "которая",
        "которые",
        "одного",
        "нового",
        "and",
        "but",
        "or",
        "with",
        "without",
        "into",
        "for",
        "to",
        "of",
        "one",
        "single",
    }
    last_word = clean.split()[-1]
    return last_word in trailing_words


def build_tehnio_hashtags(item: CandidateItem, analysis: NewsAnalysis, max_items: int) -> list[str]:
    if item.generated_hashtags:
        generated_tags: list[str] = []
        seen: set[str] = set()
        for raw in item.generated_hashtags:
            clean = normalize_tehnio_tag(raw)
            if not clean or clean in seen:
                continue
            seen.add(clean)
            generated_tags.append(clean)

        base_tags = ["tech", "tehno"][:max_items]
        primary_tags = [tag for tag in generated_tags if tag not in {"tech", "tehno"}]
        room_for_primary = max(0, max_items - len(base_tags))
        return [*primary_tags[:room_for_primary], *base_tags][:max_items]

    haystack = f"{item.title} {item.summary}".lower()
    tags: list[str] = []
    seen: set[str] = set()

    def append(tag: str) -> None:
        clean = normalize_tehnio_tag(tag)
        if not clean or clean in seen:
            return
        seen.add(clean)
        tags.append(clean)

    model_tag = normalize_tehnio_tag(extract_model_hashtag(f"{item.title}. {item.summary}"))
    if model_tag:
        append(model_tag)

    for tag in detect_tehnio_brands(item):
        append(tag)

    topical_rules = (
        ("android xr", "androidxr"),
        ("vision pro", "visionpro"),
        ("gemini", "gemini"),
        ("android", "android"),
        ("iphone", "iphone"),
        ("ipad", "ipad"),
        ("mac", "mac"),
        ("windows", "windows"),
        ("vr", "vr"),
        ("ar", "ar"),
        ("xr", "xr"),
        ("ai", "ai"),
        ("chip", "chips"),
        ("processor", "chips"),
        ("airpods", "airpods"),
        ("wearable", "wearables"),
    )
    for phrase, tag in topical_rules:
        if phrase_in_text(haystack, phrase):
            append(tag)

    append("tech")
    append("tehno")
    base_tags = ["tech", "tehno"][:max_items]
    primary_tags = [tag for tag in tags if tag not in {"tech", "tehno"}]
    room_for_primary = max(0, max_items - len(base_tags))
    return [*primary_tags[:room_for_primary], *base_tags][:max_items]


def render_tehnio_hashtags(tags: list[str]) -> str:
    return " ".join(f"#{escape_text(tag)}" for tag in tags if tag)


def normalize_tehnio_tag(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "", (value or "").lower())
    if len(clean) < 2:
        return ""
    return clean[:24]


def strip_wrapping_quotes(value: str) -> str:
    clean = (value or "").strip()
    clean = clean.strip("«»\"' ")
    return clean


def detect_tehnio_primary_brand(item: CandidateItem) -> str:
    brands = detect_tehnio_brands(item)
    return brands[0] if brands else ""


def detect_tehnio_brands(item: CandidateItem, max_items: int = 4) -> list[str]:
    haystack = f"{item.title} {item.summary}".lower()
    matches: list[tuple[int, str]] = []
    seen: set[str] = set()
    for phrase, tag in BRAND_TAGS:
        index = haystack.find(phrase)
        if index == -1 or tag in seen:
            continue
        seen.add(tag)
        matches.append((index, tag))
    matches.sort(key=lambda value: value[0])
    return [tag for _index, tag in matches[:max_items]]


def truncate_story_text(text: str, limit: int) -> str:
    normalized = normalize_story_text(text)
    if len(normalized) <= limit:
        return normalized

    snippet = normalized[:limit].rsplit(" ", 1)[0].strip()
    if not snippet:
        snippet = normalized[:limit].strip()
    return f"{snippet}..."


def normalize_story_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    paragraphs = [part.strip() for part in re.split(r"\n{2,}", raw) if part.strip()]
    if not paragraphs:
        paragraphs = [raw]

    normalized: list[str] = []
    for paragraph in paragraphs:
        normalized.append(neutralize_text(paragraph))

    return "\n\n".join(normalized)


def format_russian_date(value) -> str:
    month = RUSSIAN_MONTHS.get(value.month, str(value.month))
    return f"{value.day} {month} {value.year}, {value.strftime('%H:%M UTC')}"


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text

    snippet = text[:limit].rsplit(" ", 1)[0].strip()
    if not snippet:
        snippet = text[:limit].strip()
    return f"{snippet}..."
