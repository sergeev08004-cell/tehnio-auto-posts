from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace

from news_bot.config import AppConfig
from news_bot.models import CandidateItem


PERSONA_STYLES = {
    "Диоген Синопский": "Дерзкий, циничный, презирает роскошь и продуктовый пафос.",
    "Архимед Сиракузский": "Одержим механизмами, чипами, мощностью и инженерным смыслом.",
    "Геродот": "Рассудительный летописец слухов и подтверждений, любит начинать с 'Говорят, что...'.",
}
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")


class StoryEnhancer:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.cache: dict[str, CandidateItem] = {}

    def enhance(self, item: CandidateItem, verbose: bool = False) -> CandidateItem:
        cached = self.cache.get(item.fingerprint)
        if cached is not None:
            return cached

        selected_persona = choose_persona(item)
        fallback_comment = build_fallback_persona_comment(
            item,
            persona_name=selected_persona,
            max_chars=self.config.llm.persona_max_chars
        )
        enhanced = replace(
            item,
            persona_name=selected_persona,
            persona_comment=fallback_comment
        )

        if not self.config.editorial.persona_comments_enabled:
            self.cache[item.fingerprint] = enhanced
            return enhanced

        llm_requested = self.config.llm.enabled or bool(self.config.llm.api_key)
        if not llm_requested or not self.config.llm.api_key:
            self.cache[item.fingerprint] = enhanced
            return enhanced

        try:
            payload = self._generate_payload(item, selected_persona)
            headline = normalize_headline(str(payload.get("headline", "") or ""))
            intro = normalize_intro(
                str(payload.get("intro", "") or ""),
                max_sentences=min(self.config.llm.summary_max_sentences, 3)
            )
            facts = normalize_fact_lines(payload.get("facts"), max_items=4)
            comment = normalize_comment(
                payload.get("comment", ""),
                max_chars=self.config.llm.persona_max_chars
            )
            hashtags = normalize_hashtags(payload.get("hashtags"), max_items=8)
        except Exception as error:
            if verbose:
                print(f"[llm] source={item.source_name} error={error}")
            self.cache[item.fingerprint] = enhanced
            return enhanced

        updated = enhanced
        if headline:
            updated = replace(updated, generated_headline=headline)
        if intro:
            updated = replace(updated, summary=intro, generated_intro=intro)
        if facts:
            updated = replace(updated, generated_facts=facts)
        if comment:
            updated = replace(updated, persona_comment=comment)
        if hashtags:
            updated = replace(updated, generated_hashtags=hashtags)

        self.cache[item.fingerprint] = updated
        return updated

    def _generate_payload(self, item: CandidateItem, persona_name: str) -> dict:
        persona_style = PERSONA_STYLES.get(persona_name, "")
        system_prompt = (
            "Ты редактор русскоязычного Telegram-канала о гаджетах и технологиях. "
            "Верни только JSON без пояснений. "
            "JSON должен иметь поля headline, intro, facts, comment и hashtags. "
            "headline: короткий сильный заголовок на русском, 6-12 слов, без кликбейта. "
            "intro: 2-3 предложения на русском, коротко и по сути, единым связным абзацем. "
            "facts: массив из 3-4 коротких фактов без маркеров списка и без точки в конце. "
            "comment: одна короткая цитатная реплика выбранного персонажа, 1-2 предложения, до 220 символов. "
            "hashtags: массив из 4-8 lowercase latin tags без символа #. "
            "Не выдумывай факты, цифры и партнеров, которых нет в исходных данных. "
            "Не пиши обрывками и не копируй сырой машинный перевод. "
            "Текст должен быть живым, чистым и редакторским."
        )
        user_prompt = (
            f"Тип поста: {item.post_label or 'новость'}\n"
            f"Источник: {item.source_name}\n"
            f"Тип источника: {item.source_kind}\n"
            f"Тема: {item.topic_label}\n"
            f"Заголовок: {item.title}\n"
            f"Сводка: {item.summary}\n"
            f"Credibility: {item.credibility}\n"
            f"Выбранный персонаж: {persona_name}\n"
            f"Стиль персонажа: {persona_style}\n"
            "Сделай headline, intro и facts фактологичными. Если это инсайд, дай понять, что данные предварительные. "
            "Если это подтвержденная новость, пиши увереннее. "
            "Не перенасыщай comment театральностью: пусть реплика будет умной, образной и уместной, а не карикатурной. "
            "Если данных мало, лучше написать короче, чем додумывать детали. "
            "Ориентир по формату поста:\n"
            "✅ НОВОСТЬ: Google готовит конкурента Vision Pro — устройства Android XR\n\n"
            "Google совместно с партнёрами работает над новой платформой Android XR, которая должна стать ответом Apple Vision Pro.\n\n"
            "📌 Что известно:\n"
            "— новая платформа Android XR для VR/AR\n"
            "— ожидается интеграция с Gemini AI\n\n"
            "💬 Архимед:\n"
            "«...». \n\n"
            "#google #androidxr #vr #ar #tech #tehno\n"
            "В comment пиши только за выбранного персонажа."
        )

        if self.config.llm.provider == "gemini":
            return self._call_gemini(system_prompt, user_prompt)
        return self._call_openai(system_prompt, user_prompt)

    def _call_openai(self, system_prompt: str, user_prompt: str) -> dict:
        endpoint = self.config.llm.base_url or "https://api.openai.com/v1/chat/completions"
        request_payload = {
            "model": self.config.llm.model,
            "temperature": self.config.llm.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.llm.api_key}",
                "User-Agent": self.config.user_agent,
            },
            method="POST",
        )
        return self._parse_json_response(request, extractor=extract_openai_text)

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> dict:
        endpoint = self.config.llm.base_url or (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(self.config.llm.model)}:generateContent?key={urllib.parse.quote(self.config.llm.api_key)}"
        )
        request_payload = {
            "systemInstruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": self.config.llm.temperature,
                "responseMimeType": "application/json",
            },
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": self.config.user_agent,
            },
            method="POST",
        )
        return self._parse_json_response(request, extractor=extract_gemini_text)

    def _parse_json_response(self, request: urllib.request.Request, extractor) -> dict:
        try:
            with urllib.request.urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {error.code}: {details}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"LLM connection error: {error.reason}") from error

        raw_text = extractor(payload)
        if not raw_text:
            raise RuntimeError("LLM response did not contain text")
        return extract_json_object(raw_text)


def choose_persona(item: CandidateItem) -> str:
    order = persona_priority(item)
    seed = int(hashlib.sha256(item.fingerprint.encode("utf-8")).hexdigest()[:8], 16)
    index = seed % len(order)
    return order[index]


def persona_priority(item: CandidateItem) -> tuple[str, ...]:
    haystack = f"{item.title} {item.summary}".lower()
    insider_story = item.source_kind == "insider" or "ИНСАЙД" in (item.post_label or "").upper()

    if insider_story:
        return ("Геродот", "Геродот", "Архимед Сиракузский", "Диоген Синопский")
    if item.topic in {"gadgets", "new_models"}:
        return ("Архимед Сиракузский", "Архимед Сиракузский", "Диоген Синопский", "Геродот")
    if item.topic in {"technology"}:
        return ("Архимед Сиракузский", "Архимед Сиракузский", "Геродот", "Диоген Синопский")
    if item.topic in {"prices"} or any(marker in haystack for marker in ("price", "pricing", "цена", "стоим")):
        return ("Диоген Синопский", "Диоген Синопский", "Архимед Сиракузский", "Геродот")
    return ("Диоген Синопский", "Архимед Сиракузский", "Геродот", "Архимед Сиракузский")


def extract_openai_text(payload: dict) -> str:
    choices = payload.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text") or item.get("content") or ""
            if text:
                parts.append(str(text))
        return "\n".join(parts).strip()
    return ""


def extract_gemini_text(payload: dict) -> str:
    candidates = payload.get("candidates", [])
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    collected: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text", "")
        if text:
            collected.append(str(text))
    return "\n".join(collected).strip()


def extract_json_object(raw_text: str) -> dict:
    cleaned = CODE_FENCE_RE.sub("", raw_text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError("LLM output did not contain JSON")
    candidate = cleaned[start : end + 1]
    return json.loads(candidate)


def normalize_intro(value: str, max_sentences: int) -> str:
    parts = [normalize_text(part) for part in SENTENCE_SPLIT_RE.split(value or "") if normalize_text(part)]
    if not parts:
        return ""
    summary = " ".join(parts[:max_sentences]).strip()
    return truncate_text(summary, 420)


def normalize_headline(value: str) -> str:
    clean = normalize_text(value).strip(" .")
    if not clean:
        return ""
    if len(clean.split()) > 12:
        clean = " ".join(clean.split()[:12]).strip(" .")
    return clean


def normalize_fact_lines(payload, max_items: int) -> list[str]:
    if isinstance(payload, list):
        raw_items = [str(item or "") for item in payload]
    elif isinstance(payload, str):
        raw_items = [part for part in re.split(r"\n+", payload) if part.strip()]
    else:
        return []

    facts: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        clean = normalize_text(raw).lstrip("-•— ").rstrip(".")
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        facts.append(clean)
        if len(facts) >= max_items:
            break
    return facts


def normalize_comment(value, max_chars: int) -> str:
    clean = normalize_text(str(value or ""))
    if not clean:
        return ""
    return truncate_text(clean, max_chars)


def normalize_hashtags(payload, max_items: int) -> list[str]:
    if isinstance(payload, list):
        raw_items = [str(item or "") for item in payload]
    elif isinstance(payload, str):
        raw_items = [part for part in re.split(r"[\s,]+", payload) if part.strip()]
    else:
        return []

    tags: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        clean = raw.strip().lstrip("#").lower()
        clean = re.sub(r"[^a-z0-9]+", "", clean)
        if len(clean) < 2 or clean in seen:
            continue
        seen.add(clean)
        tags.append(clean)
        if len(tags) >= max_items:
            break
    return tags


def build_fallback_persona_comment(item: CandidateItem, persona_name: str, max_chars: int) -> str:
    subject = extract_subject(item)
    focus = detect_focus(item)
    first_fact = extract_first_fact(item)
    fact_clause = strip_terminal_punctuation(first_fact)
    insider_story = item.source_kind == "insider" or "ИНСАЙД" in (item.post_label or "").upper()

    if persona_name == "Архимед Сиракузский":
        comment = (
            f"Эврика тут не в шуме, а в механике: {fact_clause}. "
            f"Если дело правда в {focus}, вот это и есть инженерный смысл."
        )
    elif persona_name == "Геродот":
        comment = herodotus_line(subject, first_fact, insider_story)
    else:
        comment = (
            f"Вокруг {subject} снова столько церемонии, будто без этого мир встанет. "
            f"Если все опять сводится к {focus}, пафоса тут явно больше, чем пользы."
        )

    return truncate_text(comment, max_chars)


def herodotus_line(subject: str, first_fact: str, insider_story: bool) -> str:
    if insider_story:
        return (
            f"Говорят, что история вокруг {subject} только набирает ход. "
            f"Пока {first_fact.lower()}, но летописец подождал бы еще одного подтверждения."
        )
    return (
        f"Говорят, что {first_fact.lower()}. "
        f"Для сюжета вокруг {subject} это уже не шепот, а заметная запись на полях истории."
    )


def extract_subject(item: CandidateItem) -> str:
    subject = normalize_text(item.title)
    for separator in (" — ", " – ", ":", " - "):
        if separator in subject:
            head = normalize_text(subject.split(separator, 1)[0])
            if len(head) >= 4:
                return head
    if len(subject.split()) > 7:
        subject = " ".join(subject.split()[:5])
    if subject:
        return subject
    if item.topic_label:
        return item.topic_label.lower()
    return "этой новостью"


def detect_focus(item: CandidateItem) -> str:
    haystack = f"{item.title} {item.summary}".lower()
    if any(marker in haystack for marker in ("price", "pricing", "цена", "стоим")):
        return "цене"
    if any(marker in haystack for marker in ("chip", "processor", "gpu", "cpu", "чип", "процессор")):
        return "чипе и производительности"
    if any(marker in haystack for marker in ("camera", "камера", "photo", "фото")):
        return "камере"
    if any(marker in haystack for marker in ("display", "screen", "экран", "диспле")):
        return "экране"
    if any(marker in haystack for marker in ("battery", "charging", "батар", "заряд")):
        return "батарее и зарядке"
    if any(marker in haystack for marker in ("ai", "assistant", "ии", "ассистент")):
        return "AI-функциях"
    return "практической пользе"


def extract_first_fact(item: CandidateItem) -> str:
    summary = normalize_text(item.summary)
    if summary:
        first = SENTENCE_SPLIT_RE.split(summary)[0]
        clean = normalize_text(first)
        if clean:
            return clean
    title = normalize_text(item.title)
    return title or "появились новые подробности"


def normalize_text(value: str) -> str:
    cleaned = (value or "").strip().strip("\"' ")
    cleaned = WHITESPACE_RE.sub(" ", cleaned)
    return cleaned


def truncate_text(value: str, max_chars: int) -> str:
    clean = normalize_text(value)
    if len(clean) <= max_chars:
        return ensure_terminal_punctuation(clean)

    snippet = clean[:max_chars].rsplit(" ", 1)[0].strip()
    if not snippet:
        snippet = clean[:max_chars].strip()
    return ensure_terminal_punctuation(f"{snippet}...")


def ensure_terminal_punctuation(value: str) -> str:
    if not value:
        return value
    if value.endswith(("...", ".", "!", "?")):
        return value
    return f"{value}."


def strip_terminal_punctuation(value: str) -> str:
    return normalize_text(value).rstrip(".!? ")
