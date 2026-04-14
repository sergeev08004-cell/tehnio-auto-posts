from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from news_bot.config import AppConfig


class Translator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.cache: dict[tuple[str, str], str] = {}

    def should_translate(self, source_language: str) -> bool:
        if not self.config.translation.enabled:
            return False

        source = (source_language or "").lower()
        target = self.config.translation.target_language.lower()
        if not source or source == target:
            return False

        allowed = self.config.translation.source_languages
        if allowed and source not in allowed:
            return False

        return True

    def translate_text(self, text: str, source_language: str) -> str:
        clean_text = text.strip()
        if not clean_text or not self.should_translate(source_language):
            return clean_text

        cache_key = (source_language.lower(), clean_text)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        translated = self._translate_google_web(clean_text, source_language.lower())
        self.cache[cache_key] = translated
        return translated

    def _translate_google_web(self, text: str, source_language: str) -> str:
        query = urllib.parse.urlencode(
            {
                "client": "gtx",
                "sl": source_language,
                "tl": self.config.translation.target_language,
                "dt": "t",
                "dj": "1",
                "q": text
            }
        )
        endpoint = f"https://translate.googleapis.com/translate_a/single?{query}"
        request = urllib.request.Request(
            endpoint,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Translation HTTP {error.code}: {details}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Translation connection error: {error.reason}") from error

        if isinstance(payload, dict):
            sentences = payload.get("sentences", [])
            translated = "".join(sentence.get("trans", "") for sentence in sentences).strip()
            if translated:
                return translated

        if isinstance(payload, list) and payload and isinstance(payload[0], list):
            translated = "".join(part[0] for part in payload[0] if part and part[0]).strip()
            if translated:
                return translated

        raise RuntimeError("Translation response did not contain translated text")
