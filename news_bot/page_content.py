from __future__ import annotations

import html
import re
import urllib.request

from news_bot.config import AppConfig


SCRIPT_STYLE_RE = re.compile(r"<(?:script|style|noscript)\b.*?</(?:script|style|noscript)>", re.IGNORECASE | re.DOTALL)
ARTICLE_BLOCK_RE = re.compile(r"<article\b[^>]*>(.*?)</article>", re.IGNORECASE | re.DOTALL)
CONTENT_BLOCK_RE = re.compile(
    r"<(?:div|section)\b[^>]+(?:class|id)=[\"'][^\"']*(article|content|post|entry|story|body)[^\"']*[\"'][^>]*>(.*?)</(?:div|section)>",
    re.IGNORECASE | re.DOTALL
)
PARAGRAPH_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
META_DESCRIPTION_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:description|description|twitter:description)["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE
)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
PROMOTIONAL_HINTS = (
    "join us",
    "register here",
    "register now",
    "buy tickets",
    "save your seat",
    "save your spot",
    "limited seats",
    "strictlyvc",
    "sign up for",
    "sign up to",
)


def fetch_page_story(url: str, config: AppConfig, max_paragraphs: int = 6) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml"
        }
    )
    with urllib.request.urlopen(request, timeout=config.request_timeout_seconds) as response:
        content_type = response.info().get_content_type()
        payload = response.read(900_000)

    if "html" not in content_type:
        return ""

    page = payload.decode("utf-8", errors="ignore")
    page = SCRIPT_STYLE_RE.sub(" ", page)

    paragraphs = []
    meta = extract_meta_description(page)
    if meta:
        paragraphs.append(meta)

    blocks = ARTICLE_BLOCK_RE.findall(page)
    if not blocks:
        blocks = [match[1] for match in CONTENT_BLOCK_RE.findall(page)]
    if not blocks:
        blocks = [page]

    for block in blocks:
        for match in PARAGRAPH_RE.findall(block):
            paragraph = clean_html_text(match)
            if not is_content_paragraph(paragraph):
                continue
            if paragraph not in paragraphs:
                paragraphs.append(paragraph)
            if len(paragraphs) >= max_paragraphs:
                return "\n\n".join(paragraphs[:max_paragraphs])

    return "\n\n".join(paragraphs[:max_paragraphs])


def extract_meta_description(page: str) -> str:
    for match in META_DESCRIPTION_RE.findall(page):
        cleaned = clean_html_text(match)
        if is_content_paragraph(cleaned, min_words=8):
            return cleaned
    return ""


def clean_html_text(value: str) -> str:
    text = html.unescape(value)
    text = TAG_RE.sub(" ", text)
    text = text.replace("\xa0", " ")
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def is_content_paragraph(text: str, min_words: int = 10) -> bool:
    if not text:
        return False
    if len(text) < 60:
        return False
    lowered = text.lower()
    if any(token in lowered for token in ("cookie", "subscribe", "newsletter", "advertis", "all rights reserved")):
        return False
    if any(token in lowered for token in PROMOTIONAL_HINTS):
        return False
    words = text.split()
    return len(words) >= min_words
