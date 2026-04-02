from __future__ import annotations

import re

from .models import ChatMessage

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "]+",
    flags=re.UNICODE,
)
PLACEHOLDER_PATTERN = re.compile(
    r"\[(?:image|img|emoji|sticker|picture|photo|图片|表情|动画表情|贴图)\]",
    flags=re.IGNORECASE,
)
WHITESPACE_PATTERN = re.compile(r"\s+")
TEXT_PATTERN = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]")


class MessageFilter:
    def filter(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        filtered_messages: list[ChatMessage] = []
        for message in messages:
            normalized_content = self._sanitize_content(message.content)
            if not normalized_content:
                continue
            message.content = normalized_content
            filtered_messages.append(message)
        return filtered_messages

    def _sanitize_content(self, content: str) -> str:
        content = PLACEHOLDER_PATTERN.sub(" ", content)
        content = EMOJI_PATTERN.sub("", content)
        content = WHITESPACE_PATTERN.sub(" ", content).strip(" -")
        if not content:
            return ""
        if not TEXT_PATTERN.search(content):
            return ""
        return content
