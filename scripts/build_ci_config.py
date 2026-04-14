#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build GitHub Actions config for Auto News Bot")
    parser.add_argument("--base", default="config.example.json", help="Base config JSON")
    parser.add_argument("--output", default="config.ci.json", help="Output config JSON")
    return parser.parse_args()


def getenv_required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    args = parse_args()
    base_path = Path(args.base).resolve()
    output_path = Path(args.output).resolve()

    payload = json.loads(base_path.read_text(encoding="utf-8"))

    bot_token = getenv_required("TELEGRAM_BOT_TOKEN")
    channel_id = getenv_required("TELEGRAM_CHANNEL_ID")
    publication_title = os.environ.get("AUTO_NEWS_PUBLICATION_TITLE", "").strip()
    subscribe_cta_text = os.environ.get("AUTO_NEWS_SUBSCRIBE_CTA_TEXT", "").strip()
    link_text = os.environ.get("AUTO_NEWS_LINK_TEXT", "").strip()
    openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    openai_model = os.environ.get("OPENAI_MODEL", "").strip()
    max_posts_per_cycle = os.environ.get("AUTO_NEWS_MAX_POSTS_PER_CYCLE", "").strip()
    min_publish_gap_minutes = os.environ.get("AUTO_NEWS_MIN_PUBLISH_GAP_MINUTES", "").strip()
    if channel_id.startswith("@"):
        user_agent = f"AutoNewsBot/1.0 (+https://t.me/{channel_id.lstrip('@')})"
    else:
        user_agent = "AutoNewsBot/1.0 (+https://github.com/actions)"

    payload["telegram"]["bot_token"] = bot_token
    payload["telegram"]["channel_id"] = channel_id
    payload["database_path"] = "state/news.db"
    payload["publication_title"] = publication_title
    payload["user_agent"] = user_agent
    if payload.get("editorial"):
        if subscribe_cta_text:
            payload["editorial"]["subscribe_cta_text"] = subscribe_cta_text
        if link_text:
            payload["editorial"]["link_text"] = link_text
    if payload.get("llm"):
        payload["llm"]["enabled"] = bool(openai_api_key)
        if openai_model:
            payload["llm"]["model"] = openai_model
    if max_posts_per_cycle:
        payload["max_posts_per_cycle"] = max(1, int(max_posts_per_cycle))
    if min_publish_gap_minutes:
        payload["min_publish_gap_minutes"] = max(0, int(min_publish_gap_minutes))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
