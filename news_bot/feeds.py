from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

from news_bot.config import AppConfig, SourceConfig


HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
IMG_SRC_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
VIDEO_SRC_RE = re.compile(r"<video[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
SOURCE_SRC_RE = re.compile(r"<source[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
MEDIA_NAMESPACE = "http://search.yahoo.com/mrss/"


@dataclass(frozen=True)
class FeedEntry:
    source_name: str
    source_group: str
    source_language: str
    source_weight: float
    title: str
    summary: str
    url: str
    image_url: str
    published_at: datetime
    video_url: str = ""


def fetch_feed(source: SourceConfig, config: AppConfig) -> List[FeedEntry]:
    request = urllib.request.Request(
        source.url,
        headers={
            "User-Agent": config.user_agent,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"
        }
    )
    with urllib.request.urlopen(request, timeout=config.request_timeout_seconds) as response:
        payload = response.read()

    root = ET.fromstring(payload)
    tag = _local_name(root.tag)

    if tag == "rss":
        return _parse_rss(root, source)
    if tag == "feed":
        return _parse_atom(root, source)

    raise ValueError(f"Unsupported feed root tag: {root.tag}")


def _parse_rss(root: ET.Element, source: SourceConfig) -> List[FeedEntry]:
    items = []
    channel = root.find("channel")
    if channel is None:
        return items

    for node in channel.findall("item"):
        try:
            raw_description = _node_text(node, "description")
            raw_content = _node_text(node, "{http://purl.org/rss/1.0/modules/content/}encoded")
            title = clean_text(_node_text(node, "title"))
            url = clean_text(_node_text(node, "link"))
            summary = clean_text(
                raw_description
                or raw_content
            )
            image_url = extract_rss_image(node, raw_description, raw_content, source.url)
            video_url = extract_rss_video(node, raw_description, raw_content, source.url)
            published_at = parse_datetime(
                _node_text(node, "pubDate")
                or _node_text(node, "{http://purl.org/dc/elements/1.1/}date")
            )

            if not title or not url:
                continue

            items.append(
                FeedEntry(
                    source_name=source.name,
                    source_group=source.group,
                    source_language=source.language,
                    source_weight=source.weight,
                    title=title,
                    summary=summary,
                    url=url,
                    image_url=image_url,
                    published_at=published_at,
                    video_url=video_url
                )
            )
        except Exception:
            continue

    return items


def _parse_atom(root: ET.Element, source: SourceConfig) -> List[FeedEntry]:
    items = []
    namespace = _namespace(root.tag)

    for node in root.findall(f"{{{namespace}}}entry"):
        try:
            raw_summary = _node_text(node, f"{{{namespace}}}summary")
            raw_content = _node_text(node, f"{{{namespace}}}content")
            title = clean_text(_node_text(node, f"{{{namespace}}}title"))
            summary = clean_text(
                raw_summary
                or raw_content
            )
            published_at = parse_datetime(
                _node_text(node, f"{{{namespace}}}published")
                or _node_text(node, f"{{{namespace}}}updated")
            )

            url = ""
            image_url = ""
            video_url = ""
            for link in node.findall(f"{{{namespace}}}link"):
                href = clean_text(link.attrib.get("href", ""))
                relation = link.attrib.get("rel", "alternate")
                media_type = link.attrib.get("type", "")
                if href and relation == "alternate":
                    url = href
                elif href and relation == "enclosure" and is_image_candidate(href, media_type):
                    image_url = absolutize_url(href, source.url)
                elif href and relation == "enclosure" and is_video_candidate(href, media_type):
                    video_url = absolutize_url(href, source.url)

            if not image_url:
                image_url = extract_atom_image(node, raw_summary, raw_content, source.url, namespace)
            if not video_url:
                video_url = extract_atom_video(node, raw_summary, raw_content, source.url, namespace)

            if not title or not url:
                continue

            items.append(
                FeedEntry(
                    source_name=source.name,
                    source_group=source.group,
                    source_language=source.language,
                    source_weight=source.weight,
                    title=title,
                    summary=summary,
                    url=url,
                    image_url=image_url,
                    published_at=published_at,
                    video_url=video_url
                )
            )
        except Exception:
            continue

    return items


def parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)

    raw = value.strip()
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass

    iso_candidate = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def clean_text(value: Optional[str]) -> str:
    if not value:
        return ""

    text = html.unescape(value)
    text = HTML_TAG_RE.sub(" ", text)
    text = text.replace("\xa0", " ")
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def extract_rss_image(node: ET.Element, description: str, content: str, base_url: str) -> str:
    candidates = []

    for enclosure in node.findall("enclosure"):
        candidates.append(
            maybe_image_url(
                enclosure.attrib.get("url", ""),
                enclosure.attrib.get("type", ""),
                base_url
            )
        )

    for tag_name in ("content", "thumbnail"):
        for media_node in node.findall(f"{{{MEDIA_NAMESPACE}}}{tag_name}"):
            candidates.append(
                maybe_image_url(
                    media_node.attrib.get("url", ""),
                    media_node.attrib.get("type", ""),
                    base_url
                )
            )

    media_group = node.find(f"{{{MEDIA_NAMESPACE}}}group")
    if media_group is not None:
        for media_node in media_group:
            candidates.append(
                maybe_image_url(
                    media_node.attrib.get("url", ""),
                    media_node.attrib.get("type", ""),
                    base_url
                )
            )

    candidates.append(extract_image_from_html(description, base_url))
    candidates.append(extract_image_from_html(content, base_url))
    return first_non_empty(candidates)


def extract_rss_video(node: ET.Element, description: str, content: str, base_url: str) -> str:
    candidates = []

    for enclosure in node.findall("enclosure"):
        candidates.append(
            maybe_video_url(
                enclosure.attrib.get("url", ""),
                enclosure.attrib.get("type", ""),
                base_url
            )
        )

    for tag_name in ("content", "thumbnail"):
        for media_node in node.findall(f"{{{MEDIA_NAMESPACE}}}{tag_name}"):
            candidates.append(
                maybe_video_url(
                    media_node.attrib.get("url", ""),
                    media_node.attrib.get("type", ""),
                    base_url
                )
            )

    media_group = node.find(f"{{{MEDIA_NAMESPACE}}}group")
    if media_group is not None:
        for media_node in media_group:
            candidates.append(
                maybe_video_url(
                    media_node.attrib.get("url", ""),
                    media_node.attrib.get("type", ""),
                    base_url
                )
            )

    candidates.append(extract_video_from_html(description, base_url))
    candidates.append(extract_video_from_html(content, base_url))
    return first_non_empty(candidates)


def extract_atom_image(
    node: ET.Element,
    summary: str,
    content: str,
    base_url: str,
    namespace: str
) -> str:
    candidates = []

    for tag_name in ("content", "thumbnail"):
        for media_node in node.findall(f"{{{MEDIA_NAMESPACE}}}{tag_name}"):
            candidates.append(
                maybe_image_url(
                    media_node.attrib.get("url", ""),
                    media_node.attrib.get("type", ""),
                    base_url
                )
            )

    for link in node.findall(f"{{{namespace}}}link"):
        candidates.append(
            maybe_image_url(
                link.attrib.get("href", ""),
                link.attrib.get("type", ""),
                base_url
            )
        )

    candidates.append(extract_image_from_html(summary, base_url))
    candidates.append(extract_image_from_html(content, base_url))
    return first_non_empty(candidates)


def extract_atom_video(
    node: ET.Element,
    summary: str,
    content: str,
    base_url: str,
    namespace: str
) -> str:
    candidates = []

    for tag_name in ("content", "thumbnail"):
        for media_node in node.findall(f"{{{MEDIA_NAMESPACE}}}{tag_name}"):
            candidates.append(
                maybe_video_url(
                    media_node.attrib.get("url", ""),
                    media_node.attrib.get("type", ""),
                    base_url
                )
            )

    for link in node.findall(f"{{{namespace}}}link"):
        candidates.append(
            maybe_video_url(
                link.attrib.get("href", ""),
                link.attrib.get("type", ""),
                base_url
            )
        )

    candidates.append(extract_video_from_html(summary, base_url))
    candidates.append(extract_video_from_html(content, base_url))
    return first_non_empty(candidates)


def extract_image_from_html(value: str, base_url: str) -> str:
    if not value:
        return ""

    match = IMG_SRC_RE.search(value)
    if not match:
        return ""

    return absolutize_url(match.group(1), base_url)


def extract_video_from_html(value: str, base_url: str) -> str:
    if not value:
        return ""

    match = VIDEO_SRC_RE.search(value)
    if match:
        return absolutize_url(match.group(1), base_url)

    match = SOURCE_SRC_RE.search(value)
    if match:
        candidate = absolutize_url(match.group(1), base_url)
        if is_video_candidate(candidate, ""):
            return candidate

    return ""


def maybe_image_url(url: str, media_type: str, base_url: str) -> str:
    if not url:
        return ""

    if is_image_candidate(url, media_type):
        return absolutize_url(url, base_url)

    return ""


def maybe_video_url(url: str, media_type: str, base_url: str) -> str:
    if not url:
        return ""

    if is_video_candidate(url, media_type):
        return absolutize_url(url, base_url)

    return ""


def is_image_candidate(url: str, media_type: str) -> bool:
    lowered_type = (media_type or "").lower()
    lowered_url = url.lower()
    if lowered_type.startswith("image/"):
        return True

    return lowered_url.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))


def is_video_candidate(url: str, media_type: str) -> bool:
    lowered_type = (media_type or "").lower()
    lowered_url = url.lower()
    if lowered_type.startswith("video/"):
        return True

    return lowered_url.endswith((".mp4", ".mov", ".webm", ".m4v"))


def absolutize_url(url: str, base_url: str) -> str:
    if not url:
        return ""

    clean_url = html.unescape(url.strip())
    return urllib.parse.urljoin(base_url, clean_url)


def first_non_empty(values: List[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def _local_name(tag: str) -> str:
    if "}" not in tag:
        return tag
    return tag.rsplit("}", 1)[1]


def _namespace(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def _node_text(node: ET.Element, path: str) -> str:
    child = node.find(path)
    if child is None or child.text is None:
        return ""
    return child.text
