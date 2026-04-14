#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from news_bot.config import load_config


DEFAULT_INVITE_LINK_NAMES = ["profile", "x", "youtube", "website", "partners"]
CHANNEL_DESCRIPTION = (
    "Гаджеты и технологии на русском: смартфоны, ноутбуки, AI, чипы, приложения, платформы и consumer tech. "
    "Коротко, по делу, с фактами и ссылками на первоисточники."
)
WELCOME_POST = """🧠 <b>@TehNio — гаджеты и технологии</b>

Здесь выходят:
• смартфоны, ноутбуки, наушники и носимые устройства
• AI, чипы, платформы и приложения
• большие релизы от Apple, Google, Samsung и других
• полезные цифры, характеристики и важные апдейты
• то, что реально двигает tech-рынок

Формат канала:
• коротко и по делу
• без воды и сухого официоза
• с фактами, цифрами и ссылкой на источник
• на русском языке, даже если новость зарубежная

🔗 Подписывайтесь и делитесь каналом: https://t.me/TehNio"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set up Telegram channel growth assets")
    parser.add_argument("--config", default="config.json", help="Path to JSON config file")
    parser.add_argument("--description", default=CHANNEL_DESCRIPTION, help="Channel description")
    parser.add_argument("--welcome-post", default=WELCOME_POST, help="Pinned welcome post")
    parser.add_argument(
        "--invite-links",
        default=",".join(DEFAULT_INVITE_LINK_NAMES),
        help="Comma-separated list of invite link names to create"
    )
    parser.add_argument("--skip-description", action="store_true", help="Skip updating chat description")
    parser.add_argument("--skip-welcome-post", action="store_true", help="Skip sending the welcome post")
    parser.add_argument("--skip-pin", action="store_true", help="Skip pinning the welcome post")
    parser.add_argument("--skip-links", action="store_true", help="Skip creating invite links")
    return parser.parse_args()


def call_bot_api(config, method: str, payload: dict[str, object]) -> dict:
    endpoint = f"https://api.telegram.org/bot{config.telegram.bot_token}/{method}"
    encoded_payload = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=encoded_payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": config.user_agent,
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=config.request_timeout_seconds) as response:
        data = json.loads(response.read().decode("utf-8"))

    if not data.get("ok"):
        raise RuntimeError(f"Telegram API rejected {method}: {data}")
    return data


def update_description(config, description: str) -> None:
    call_bot_api(
        config,
        "setChatDescription",
        {
            "chat_id": config.telegram.channel_id,
            "description": description[:255],
        },
    )


def send_welcome_post(config, message: str) -> int:
    data = call_bot_api(
        config,
        "sendMessage",
        {
            "chat_id": config.telegram.channel_id,
            "text": message,
            "parse_mode": config.telegram.parse_mode,
            "disable_web_page_preview": "true",
        },
    )
    return int(data["result"]["message_id"])


def pin_message(config, message_id: int) -> None:
    call_bot_api(
        config,
        "pinChatMessage",
        {
            "chat_id": config.telegram.channel_id,
            "message_id": message_id,
            "disable_notification": "true",
        },
    )


def create_invite_link(config, name: str) -> str:
    data = call_bot_api(
        config,
        "createChatInviteLink",
        {
            "chat_id": config.telegram.channel_id,
            "name": name[:32],
        },
    )
    return str(data["result"]["invite_link"])


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)

    invite_names = [item.strip() for item in args.invite_links.split(",") if item.strip()]

    if not args.skip_description:
        update_description(config, args.description)
        print("Updated channel description")

    message_id = 0
    if not args.skip_welcome_post:
        message_id = send_welcome_post(config, args.welcome_post)
        print(f"Published welcome post: {message_id}")

    if message_id and not args.skip_pin:
        pin_message(config, message_id)
        print(f"Pinned message: {message_id}")

    if not args.skip_links:
        for name in invite_names:
            invite_link = create_invite_link(config, name)
            print(f"{name}: {invite_link}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
