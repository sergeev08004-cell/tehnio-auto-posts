#!/usr/bin/env python3

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

from news_bot.config import load_config
from news_bot.formatter import detect_brand_label, format_caption, format_post
from news_bot.page_content import fetch_page_story
from news_bot.page_images import fetch_page_images, fetch_page_videos
from news_bot.ranking import rank_candidates
from news_bot.storage import Storage
from news_bot.story_ai import StoryEnhancer
from news_bot.telegram_api import TelegramPublisher
from news_bot.text_tools import tokens_from_text
from news_bot.translation import Translator
from news_bot.worker import collect_candidates


ACCIDENT_VISUAL_VIDEO_HINTS = (
    "dashcam",
    "dash cam",
    "caught on camera",
    "caught on video",
    "video shows",
    "footage shows",
    "footage of the crash",
    "surveillance",
    "security camera",
    "traffic camera",
    "traffic cam",
    "bodycam",
    "body cam",
    "camera captured",
    "camera shows",
    "captured the moment",
    "video of the crash",
    "crash footage",
    "collision footage",
    "момент дтп",
    "попало на видео",
    "кадры дтп",
    "видеорегистратор",
    "регистратор",
    "камера наблюдения",
    "запись с камеры",
)
ACCIDENT_REPORT_ONLY_HINTS = (
    "police said",
    "police say",
    "according to police",
    "authorities said",
    "officials said",
    "state police",
    "troopers say",
    "sheriff said",
    "news conference",
    "press conference",
    "police warning",
    "police statement",
    "statement from police",
    "comments from police",
    "брифинг полиции",
    "полиция сообщила",
    "по данным полиции",
    "заявили в полиции",
    "комментарий полиции",
)
MERGE_RELEVANCE_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "about",
    "after",
    "before",
    "have",
    "has",
    "had",
    "will",
    "your",
    "their",
    "they",
    "them",
    "more",
    "than",
    "что",
    "это",
    "как",
    "для",
    "после",
    "перед",
    "если",
    "когда",
    "того",
    "теперь",
    "только",
    "также",
    "новый",
    "новая",
    "новое",
    "компания",
    "сервис",
    "рынок",
}
PROMOTIONAL_PARAGRAPH_HINTS = (
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto automotive news Telegram bot")
    parser.add_argument("--config", default="config.json", help="Path to JSON config file")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Do not publish to Telegram")
    parser.add_argument("--verbose", action="store_true", help="Print extended cycle logs")
    return parser.parse_args()


def run_cycle(storage: Storage, publisher: TelegramPublisher, dry_run: bool, verbose: bool) -> int:
    config = publisher.config
    translator = Translator(config)
    enhancer = StoryEnhancer(config)
    candidates = collect_candidates(config, storage, verbose=verbose)
    rank_window = max(config.max_posts_per_cycle * 4, config.max_posts_per_cycle + 5)
    ranked = rank_candidates(
        candidates,
        storage=storage,
        allowed_topics=config.allowed_topics,
        priority_topics=config.priority_topics,
        max_age_hours=config.max_post_age_hours,
        min_age_minutes=config.min_post_age_minutes,
        max_items=rank_window,
        diversity=config.diversity
    )

    if verbose:
        print(f"[cycle] candidates={len(candidates)} ranked={len(ranked)} dry_run={dry_run}")

    published = 0
    publish_errors = 0
    last_publish_error: Exception | None = None
    for item in ranked:
        if published >= config.max_posts_per_cycle:
            break

        if not dry_run and not storage.can_publish_now(config.min_publish_gap_minutes):
            if verbose:
                print("[cycle] publish gap active, postponing remaining items")
            break

        item = enrich_item_content(item, config, verbose=verbose)
        item, image_urls, video_url = enrich_item_media(item, config, verbose=verbose)
        item = localize_item(item, translator, verbose=verbose)
        item = enhancer.enhance(item, verbose=verbose)
        if not video_url and not image_urls:
            if verbose:
                print(f"[media] source={item.source_name} skipped: no video or photo")
            continue
        message = format_post(item, config, config.telegram.channel_id)
        caption = format_caption(item, config, config.telegram.channel_id)
        album_label = detect_brand_label(item)
        if dry_run:
            print("=" * 72)
            print(message)
            if video_url:
                print("")
                print(f"Видео: {video_url}")
            if image_urls:
                print("")
                for index, image_url in enumerate(image_urls, start=1):
                    print(f"Картинка {index}: {image_url}")
                    if index in (2, 3):
                        print(f"Подпись {index}: {album_label}")
            print("=" * 72)
        else:
            try:
                publisher.publish(
                    message,
                    video_url=video_url,
                    image_url=item.image_url,
                    image_urls=image_urls,
                    caption=caption,
                    album_label=album_label
                )
            except Exception as error:
                publish_errors += 1
                last_publish_error = error
                if verbose:
                    print(f"[publish] source={item.source_name} error={error}")
                continue
            storage.mark_published(item)

        published += 1

        if verbose:
            action = "prepared" if dry_run else "published"
            print(f"[cycle] {action} fingerprint={item.fingerprint} source={item.source_name}")

    if verbose and published == 0:
        print("[cycle] nothing published")

    if not dry_run and published == 0 and publish_errors > 0 and last_publish_error is not None:
        raise RuntimeError(f"Unable to publish any items: {last_publish_error}")

    return published


def localize_item(item, translator: Translator, verbose: bool = False):
    if not translator.should_translate(item.source_language):
        return item

    try:
        translated_title = translator.translate_text(item.title, item.source_language)
        translated_summary = translate_story_text(translator, item.summary, item.source_language)
    except Exception as error:
        if verbose:
            print(f"[translate] source={item.source_name} error={error}")
        return item

    if verbose:
        print(f"[translate] source={item.source_name} translated to {translator.config.translation.target_language}")

    return replace(
        item,
        source_language=translator.config.translation.target_language,
        title=translated_title,
        summary=translated_summary
    )


def translate_story_text(translator: Translator, text: str, source_language: str) -> str:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if not paragraphs:
        return translator.translate_text(text, source_language)

    translated_paragraphs = [
        translator.translate_text(paragraph, source_language)
        for paragraph in paragraphs
    ]
    return "\n\n".join(part for part in translated_paragraphs if part.strip())


def enrich_item_media(item, config, verbose: bool = False):
    images = []
    if item.image_url:
        images.append(item.image_url)
    videos = []
    if item.video_url:
        videos.append(item.video_url)

    try:
        page_videos = fetch_page_videos(item.url, config, limit=2)
    except Exception as error:
        if verbose:
            print(f"[video] source={item.source_name} error={error}")
        page_videos = []

    for video_url in page_videos:
        if video_url not in videos:
            videos.append(video_url)

    try:
        page_images = fetch_page_images(item.url, config, limit=6)
    except Exception as error:
        if verbose:
            print(f"[image] source={item.source_name} error={error}")
        page_images = []

    for image_url in page_images:
        if image_url not in images:
            images.append(image_url)

    primary_video = pick_primary_video(item, videos)
    primary_image = images[0] if images else item.image_url

    if verbose:
        if primary_video:
            print(f"[video] source={item.source_name} videos={len(videos)} first={primary_video}")
        elif videos:
            print(f"[video] source={item.source_name} skipped: video lacks clear crash footage cues")
        if primary_image:
            print(f"[image] source={item.source_name} images={len(images)} first={primary_image}")

    return replace(item, image_url=primary_image, video_url=primary_video), images, primary_video


def enrich_item_content(item, config, verbose: bool = False):
    try:
        page_story = fetch_page_story(item.url, config, max_paragraphs=6)
    except Exception as error:
        if verbose:
            print(f"[content] source={item.source_name} error={error}")
        return item

    if not page_story:
        return item

    current_summary = (item.summary or "").strip()
    if len(page_story) <= len(current_summary):
        return item

    merged_parts = []
    title_normalized = normalize_merge_text(item.title)
    title_tokens = story_relevance_tokens(item.title)
    summary_tokens = story_relevance_tokens(current_summary)
    merged_parts = collect_story_paragraphs(
        page_story,
        title_normalized=title_normalized,
        title_tokens=title_tokens,
        summary_tokens=summary_tokens,
        source_name=item.source_name,
        verbose=verbose
    )

    if not merged_parts and current_summary:
        merged_parts = merge_short_paragraphs([current_summary])

    merged_summary = "\n\n".join(merge_short_paragraphs(merged_parts)).strip()
    if not merged_summary:
        return item

    if verbose:
        print(f"[content] source={item.source_name} summary={len(current_summary)} enriched={len(merged_summary)}")

    return replace(item, summary=merged_summary)


def normalize_merge_text(value: str) -> str:
    return " ".join((value or "").lower().split())


def merge_short_paragraphs(paragraphs: list[str]) -> list[str]:
    merged: list[str] = []
    for paragraph in paragraphs:
        cleaned = paragraph.strip()
        if not cleaned:
            continue
        if merged and len(cleaned) < 65:
            merged[-1] = f"{merged[-1]} {cleaned}".strip()
            continue
        merged.append(cleaned)
    return merged


def story_relevance_tokens(text: str) -> set[str]:
    tokens = {
        token for token in tokens_from_text(text)
        if len(token) >= 4 and token not in MERGE_RELEVANCE_STOPWORDS
    }
    return tokens


def collect_story_paragraphs(
    text: str,
    title_normalized: str,
    title_tokens: set[str],
    summary_tokens: set[str],
    source_name: str,
    verbose: bool
) -> list[str]:
    paragraphs: list[str] = []
    existing_norms: list[str] = []

    for paragraph in text.split("\n\n"):
        cleaned = paragraph.strip()
        if not cleaned:
            continue
        normalized = normalize_merge_text(cleaned)
        if not normalized:
            continue
        if title_normalized and normalized.startswith(title_normalized) and len(normalized) <= len(title_normalized) + 220:
            continue
        if paragraph_is_promotional(cleaned):
            if verbose:
                print(f"[content] source={source_name} skipped promotional paragraph")
            continue
        if (title_tokens or summary_tokens) and not paragraph_is_relevant(cleaned, title_tokens, summary_tokens):
            if verbose:
                print(f"[content] source={source_name} skipped unrelated paragraph")
            continue
        if any(
            (normalized in existing or existing in normalized) and min(len(normalized), len(existing)) >= 80
            for existing in existing_norms
        ):
            continue
        paragraphs.append(cleaned)
        existing_norms.append(normalized)

    return merge_short_paragraphs(paragraphs)


def paragraph_is_promotional(paragraph: str) -> bool:
    lowered = paragraph.lower()
    return any(token in lowered for token in PROMOTIONAL_PARAGRAPH_HINTS)


def paragraph_is_relevant(paragraph: str, title_tokens: set[str], summary_tokens: set[str]) -> bool:
    paragraph_tokens = story_relevance_tokens(paragraph)
    if not paragraph_tokens:
        return False

    title_overlap = paragraph_tokens & title_tokens
    summary_overlap = paragraph_tokens & summary_tokens

    if len(title_overlap) >= 2:
        return True

    if title_overlap and summary_overlap:
        return True

    if len(summary_overlap) >= 3:
        return True

    if any(len(token) >= 7 for token in title_overlap):
        return True

    if not summary_tokens and title_overlap and len(paragraph_tokens) <= 24:
        return True

    return False


def pick_primary_video(item, videos: list[str]) -> str:
    if not videos:
        return item.video_url
    if item.topic != "accidents":
        return videos[0]
    if accident_video_has_visual_evidence(item, videos):
        return videos[0]
    return ""


def accident_video_has_visual_evidence(item, videos: list[str]) -> bool:
    haystack = " ".join(
        filter(
            None,
            [
                item.title,
                item.summary,
                item.url,
                item.source_name,
                *videos,
            ],
        )
    ).lower()
    has_visual_hint = any(keyword in haystack for keyword in ACCIDENT_VISUAL_VIDEO_HINTS)
    if has_visual_hint:
        return True
    has_report_only_hint = any(keyword in haystack for keyword in ACCIDENT_REPORT_ONLY_HINTS)
    return not has_report_only_hint and "video" in haystack and "crash" in haystack


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    storage = Storage(config_path.parent / config.database_path)
    publisher = TelegramPublisher(config)

    if args.once:
        run_cycle(storage, publisher, dry_run=args.dry_run, verbose=args.verbose)
        return 0

    while True:
        try:
            run_cycle(storage, publisher, dry_run=args.dry_run, verbose=args.verbose)
        except KeyboardInterrupt:
            return 0
        except Exception as error:
            print(f"[error] {error}", file=sys.stderr)

        time.sleep(config.poll_interval_minutes * 60)


if __name__ == "__main__":
    raise SystemExit(main())
