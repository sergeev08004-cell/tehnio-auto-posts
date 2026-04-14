from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request

from news_bot.config import AppConfig


META_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image|twitter:image:src)["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE
)
META_VIDEO_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:video(?::secure_url)?|twitter:player:stream)["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE
)
IMG_SRC_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
VIDEO_SRC_RE = re.compile(r"<video[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
SOURCE_SRC_RE = re.compile(r"<source[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
NOISY_IMAGE_RE = re.compile(
    r"(logo|icon|sprite|avatar|favicon|banner-ad|analytics|counter|pixel|beacon|tracker|flag|promo|topline|placeholder|thumbnail)",
    re.IGNORECASE
)
TRACKING_IMAGE_HOSTS = {
    "tns-counter.ru",
    "www.tns-counter.ru",
    "counter.yadro.ru",
    "mc.yandex.ru",
    "top-fwz1.mail.ru",
    "top-fwz1.mail.ru.",
}
NOISY_VIDEO_RE = re.compile(r"(avatar|sprite|analytics|counter|pixel|beacon|tracker)", re.IGNORECASE)

def fetch_page_images(url: str, config: AppConfig, limit: int = 4) -> list[str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml"
        }
    )
    with urllib.request.urlopen(request, timeout=config.request_timeout_seconds) as response:
        content_type = response.info().get_content_type()
        payload = response.read(512_000)

    if "html" not in content_type:
        return []

    page = payload.decode("utf-8", errors="ignore")
    candidates = []

    for match in META_IMAGE_RE.findall(page):
        candidates.append(absolute_url(match, url))

    for match in IMG_SRC_RE.findall(page):
        candidates.append(absolute_url(match, url))

    return unique_images(candidates, limit=limit)


def fetch_page_videos(url: str, config: AppConfig, limit: int = 2) -> list[str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml"
        }
    )
    with urllib.request.urlopen(request, timeout=config.request_timeout_seconds) as response:
        content_type = response.info().get_content_type()
        payload = response.read(512_000)

    if "html" not in content_type:
        return []

    page = payload.decode("utf-8", errors="ignore")
    candidates = []

    for match in META_VIDEO_RE.findall(page):
        candidates.append(absolute_url(match, url))

    for match in VIDEO_SRC_RE.findall(page):
        candidates.append(absolute_url(match, url))

    for match in SOURCE_SRC_RE.findall(page):
        candidates.append(absolute_url(match, url))

    return unique_videos(candidates, limit=limit)


def fetch_page_image(url: str, config: AppConfig) -> str:
    images = fetch_page_images(url, config, limit=1)
    return images[0] if images else ""


def absolute_url(value: str, base_url: str) -> str:
    clean_value = html.unescape(value.strip())
    return urllib.parse.urljoin(base_url, clean_value)


def unique_images(candidates: list[str], limit: int) -> list[str]:
    seen = set()
    images = []

    for candidate in candidates:
        clean = candidate.strip()
        if not clean or clean.startswith("data:"):
            continue
        if is_noisy_image(clean):
            continue
        if clean in seen:
            continue
        seen.add(clean)
        images.append(clean)
        if len(images) >= limit:
            break

    return images


def unique_videos(candidates: list[str], limit: int) -> list[str]:
    seen = set()
    videos = []

    for candidate in candidates:
        clean = candidate.strip()
        if not clean or clean.startswith("data:"):
            continue
        if is_noisy_video(clean):
            continue
        if not is_video_candidate(clean):
            continue
        if clean in seen:
            continue
        seen.add(clean)
        videos.append(clean)
        if len(videos) >= limit:
            break

    return videos


def is_noisy_image(url: str) -> bool:
    if NOISY_IMAGE_RE.search(url):
        return True

    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    query = parsed.query.lower()

    if host in TRACKING_IMAGE_HOSTS:
        return True

    if any(token in host for token in ("counter", "analytics", "tracker")):
        return True

    if path.endswith(".svg"):
        return True

    if "/thumb/" in path or "/thumbnail/" in path:
        return True

    file_name = path.rsplit("/", 1)[-1]
    if file_name.startswith("tn_"):
        return True

    noise_haystack = f"{path}?{query}"
    if any(token in noise_haystack for token in ("pixel", "counter", "beacon", "analytics", "metric", "promo", "topline", "flag", "thumb")):
        return True

    return False


def is_noisy_video(url: str) -> bool:
    if NOISY_VIDEO_RE.search(url):
        return True

    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    query = parsed.query.lower()

    if host in TRACKING_IMAGE_HOSTS:
        return True

    noise_haystack = f"{path}?{query}"
    if any(token in noise_haystack for token in ("pixel", "counter", "beacon", "analytics", "tracker")):
        return True

    return False


def is_video_candidate(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path.lower()
    return path.endswith((".mp4", ".mov", ".webm", ".m4v"))
