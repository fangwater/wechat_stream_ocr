from __future__ import annotations

import re
from datetime import datetime

from .models import ChatMessage, OcrLine

BRACKETED_PATTERN = re.compile(
    r"^\[(?P<sender>[^\]]+)\]\s+\[(?P<timestamp>[^\]]+)\]\s+(?P<content>.+)$"
)
ABSOLUTE_TIME_PATTERN = re.compile(
    r"^(?P<sender>\S+)\s+(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s+(?P<content>.+)$"
)
TIME_ONLY_PATTERN = re.compile(
    r"^(?P<sender>\S+)\s+(?P<timestamp>\d{1,2}:\d{2}(?::\d{2})?)\s+(?P<content>.+)$"
)
WHITESPACE_PATTERN = re.compile(r"\s+")


class MessageParser:
    def parse(
        self,
        lines: list[OcrLine],
        received_at: datetime,
        source: str,
    ) -> list[ChatMessage]:
        messages: list[ChatMessage] = []
        for line in lines:
            text = WHITESPACE_PATTERN.sub(" ", line.text).strip()
            if not text:
                continue

            match = (
                BRACKETED_PATTERN.match(text)
                or ABSOLUTE_TIME_PATTERN.match(text)
                or TIME_ONLY_PATTERN.match(text)
            )
            if match:
                messages.append(
                    ChatMessage(
                        sender=match.group("sender"),
                        timestamp=self._normalize_timestamp(
                            match.group("timestamp"),
                            received_at,
                        ),
                        content=match.group("content").strip(),
                        source=source,
                        received_at=received_at,
                    )
                )
                continue

            if messages:
                messages[-1].content = f"{messages[-1].content} {text}".strip()
                continue

            messages.append(
                ChatMessage(
                    sender="unknown",
                    timestamp=received_at.strftime("%Y-%m-%d %H:%M:%S"),
                    content=text,
                    source=source,
                    received_at=received_at,
                )
            )
        return messages

    def _normalize_timestamp(self, raw_timestamp: str, received_at: datetime) -> str:
        raw_timestamp = raw_timestamp.strip()
        if re.fullmatch(r"\d{1,2}:\d{2}", raw_timestamp):
            return f"{received_at:%Y-%m-%d} {raw_timestamp}:00"
        if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", raw_timestamp):
            return f"{received_at:%Y-%m-%d} {raw_timestamp}"
        return raw_timestamp
