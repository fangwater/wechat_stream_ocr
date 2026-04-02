from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class FrameEnvelope:
    image_bytes: bytes
    source: str
    received_at: datetime
    message_id: str | None = None


@dataclass(frozen=True, slots=True)
class DiffResult:
    has_new_messages: bool
    changed_ratio: float
    mean_delta: float
    changed_bbox: tuple[int, int, int, int] | None = None


@dataclass(frozen=True, slots=True)
class OcrLine:
    text: str
    confidence: float | None = None
    bbox: tuple[float, float, float, float] | None = None


@dataclass(slots=True)
class ChatMessage:
    sender: str
    timestamp: str
    content: str
    source: str
    received_at: datetime

    def signature(self) -> str:
        payload = f"{self.sender}|{self.timestamp}|{self.content}"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def format_text(self) -> str:
        return f"[{self.sender}] [{self.timestamp}] {self.content}"
