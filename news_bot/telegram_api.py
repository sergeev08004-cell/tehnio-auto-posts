from __future__ import annotations

import html
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import List, Optional

from news_bot.config import AppConfig


class TelegramPublisher:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def publish(
        self,
        message: str,
        video_url: str = "",
        image_url: str = "",
        image_urls: Optional[List[str]] = None,
        caption: str = "",
        album_label: str = ""
    ) -> None:
        images = []
        for candidate in image_urls or []:
            if candidate and candidate not in images:
                images.append(candidate)
        if image_url and image_url not in images:
            images.insert(0, image_url)

        if video_url:
            try:
                self._publish_video(video_url, caption or message)
                return
            except RuntimeError as error:
                print(f"[telegram] video upload failed, retrying plain caption: {error}", file=sys.stderr)
                plain_caption = self._plain_text(caption or message)
                if plain_caption and plain_caption != (caption or message):
                    try:
                        self._publish_video(video_url, plain_caption, force_plain=True)
                        return
                    except RuntimeError as plain_error:
                        print(f"[telegram] plain video upload failed, fallback to photo: {plain_error}", file=sys.stderr)
                else:
                    print(f"[telegram] video upload failed, fallback to photo: {error}", file=sys.stderr)

        if len(images) > 1:
            print(
                f"[telegram] multiple images found ({len(images)}), using the first image with caption for reliability",
                file=sys.stderr
            )

        if images:
            try:
                self._publish_photo(images[0], caption or message)
                return
            except RuntimeError as error:
                print(f"[telegram] photo upload failed, fallback to text: {error}", file=sys.stderr)
                plain_caption = self._plain_text(caption or message)
                if plain_caption and plain_caption != (caption or message):
                    try:
                        self._publish_photo(images[0], plain_caption, force_plain=True)
                        return
                    except RuntimeError as plain_error:
                        print(
                            f"[telegram] plain photo upload failed, fallback to text: {plain_error}",
                            file=sys.stderr
                        )

        try:
            self._publish_message(message)
        except RuntimeError as error:
            plain_message = self._plain_text(message)
            if plain_message and plain_message != message:
                print(f"[telegram] rich text failed, retrying plain text: {error}", file=sys.stderr)
                self._publish_message(plain_message, force_plain=True)
                return
            raise

    def _publish_video(self, video_url: str, caption: str, force_plain: bool = False) -> None:
        video_bytes, file_name, content_type = self._download_binary(video_url, kind="video")
        boundary = f"----AutoNewsBot{uuid.uuid4().hex}"
        fields = {
            "chat_id": self.config.telegram.channel_id,
            "caption": caption,
            "supports_streaming": "true"
        }
        if self.config.telegram.parse_mode and not force_plain:
            fields["parse_mode"] = self.config.telegram.parse_mode

        body = self._build_multipart_body(
            boundary=boundary,
            fields=fields,
            file_field_name="video",
            file_name=file_name,
            file_content=video_bytes,
            file_content_type=content_type
        )

        endpoint = f"https://api.telegram.org/bot{self.config.telegram.bot_token}/sendVideo"
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": self.config.user_agent
            },
            method="POST"
        )

        raw = self._send_request(request)
        payload = json.loads(raw.decode("utf-8"))
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API rejected video: {payload}")

    def _publish_message(self, message: str, force_plain: bool = False) -> None:
        payload = {
            "chat_id": self.config.telegram.channel_id,
            "text": message,
            "disable_web_page_preview": "true" if self.config.telegram.disable_web_page_preview else "false"
        }
        if self.config.telegram.parse_mode and not force_plain:
            payload["parse_mode"] = self.config.telegram.parse_mode

        endpoint = f"https://api.telegram.org/bot{self.config.telegram.bot_token}/sendMessage"
        request = urllib.request.Request(
            endpoint,
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.config.user_agent
            },
            method="POST"
        )

        raw = self._send_request(request)
        payload = json.loads(raw.decode("utf-8"))
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API rejected message: {payload}")

    def _publish_photo(self, image_url: str, caption: str, force_plain: bool = False) -> None:
        image_bytes, file_name, content_type = self._download_binary(image_url, kind="image")
        boundary = f"----AutoNewsBot{uuid.uuid4().hex}"
        body = self._build_multipart_body(
            boundary=boundary,
            fields={
                "chat_id": self.config.telegram.channel_id,
                "caption": caption
            },
            file_field_name="photo",
            file_name=file_name,
            file_content=image_bytes,
            file_content_type=content_type
        )
        if self.config.telegram.parse_mode and not force_plain:
            body = self._build_multipart_body(
                boundary=boundary,
                fields={
                    "chat_id": self.config.telegram.channel_id,
                    "caption": caption,
                    "parse_mode": self.config.telegram.parse_mode
                },
                file_field_name="photo",
                file_name=file_name,
                file_content=image_bytes,
                file_content_type=content_type
            )

        endpoint = f"https://api.telegram.org/bot{self.config.telegram.bot_token}/sendPhoto"
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": self.config.user_agent
            },
            method="POST"
        )

        raw = self._send_request(request)
        payload = json.loads(raw.decode("utf-8"))
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API rejected photo: {payload}")

    def _publish_media_group(self, image_urls: List[str], caption: str, album_label: str = "") -> None:
        media = []
        for index, image_url in enumerate(image_urls):
            item = {
                "type": "photo",
                "media": image_url
            }
            if index == 0:
                item["caption"] = caption
                if self.config.telegram.parse_mode:
                    item["parse_mode"] = self.config.telegram.parse_mode
            elif album_label and index in (1, 2):
                item["caption"] = f"<b>{album_label}</b>"
                if self.config.telegram.parse_mode:
                    item["parse_mode"] = self.config.telegram.parse_mode
            media.append(item)

        payload = {
            "chat_id": self.config.telegram.channel_id,
            "media": json.dumps(media, ensure_ascii=False)
        }
        endpoint = f"https://api.telegram.org/bot{self.config.telegram.bot_token}/sendMediaGroup"
        request = urllib.request.Request(
            endpoint,
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.config.user_agent
            },
            method="POST"
        )

        raw = self._send_request(request)
        response_payload = json.loads(raw.decode("utf-8"))
        if not response_payload.get("ok"):
            raise RuntimeError(f"Telegram API rejected media group: {response_payload}")

    def _download_binary(self, media_url: str, kind: str) -> tuple[bytes, str, str]:
        request = urllib.request.Request(
            media_url,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "image/*,*/*;q=0.8" if kind == "image" else "video/*,*/*;q=0.8"
            }
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                content_type = response.info().get_content_type()
                media_bytes = response.read()
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{kind.capitalize()} HTTP {error.code}: {details}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"{kind.capitalize()} connection error: {error.reason}") from error

        if not content_type.startswith(f"{kind}/"):
            guessed_type = mimetypes.guess_type(media_url)[0] or ""
            content_type = guessed_type or content_type

        if not content_type.startswith(f"{kind}/"):
            raise RuntimeError(f"Unsupported {kind} content type: {content_type}")

        parsed = urllib.parse.urlsplit(media_url)
        default_name = "news-image" if kind == "image" else "news-video"
        file_name = os.path.basename(parsed.path) or default_name
        return media_bytes, file_name, content_type

    def _build_multipart_body(
        self,
        boundary: str,
        fields: dict[str, str],
        file_field_name: str,
        file_name: str,
        file_content: bytes,
        file_content_type: str
    ) -> bytes:
        buffer = bytearray()
        line_break = b"\r\n"

        for name, value in fields.items():
            buffer.extend(f"--{boundary}".encode("utf-8"))
            buffer.extend(line_break)
            buffer.extend(f'Content-Disposition: form-data; name="{name}"'.encode("utf-8"))
            buffer.extend(line_break)
            buffer.extend(line_break)
            buffer.extend(value.encode("utf-8"))
            buffer.extend(line_break)

        buffer.extend(f"--{boundary}".encode("utf-8"))
        buffer.extend(line_break)
        buffer.extend(
            f'Content-Disposition: form-data; name="{file_field_name}"; filename="{file_name}"'.encode("utf-8")
        )
        buffer.extend(line_break)
        buffer.extend(f"Content-Type: {file_content_type}".encode("utf-8"))
        buffer.extend(line_break)
        buffer.extend(line_break)
        buffer.extend(file_content)
        buffer.extend(line_break)
        buffer.extend(f"--{boundary}--".encode("utf-8"))
        buffer.extend(line_break)
        return bytes(buffer)

    def _send_request(self, request: urllib.request.Request) -> bytes:
        try:
            with urllib.request.urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Telegram API HTTP {error.code}: {details}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Telegram API connection error: {error.reason}") from error

    def _plain_text(self, message: str) -> str:
        text = re.sub(r"<tg-spoiler>.*?</tg-spoiler>", "", message, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
