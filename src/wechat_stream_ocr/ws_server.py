from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any

import websockets

from .config import AppConfig
from .models import FrameEnvelope
from .pipeline import ProcessingPipeline

logger = logging.getLogger(__name__)


class WebSocketImageServer:
    def __init__(self, config: AppConfig, pipeline: ProcessingPipeline) -> None:
        self._config = config
        self._pipeline = pipeline

    async def serve(self) -> None:
        async with websockets.serve(
            self._handle_connection,
            self._config.ws_host,
            self._config.ws_port,
            max_size=self._config.max_payload_bytes,
        ):
            logger.info(
                "WebSocket server listening on ws://%s:%s",
                self._config.ws_host,
                self._config.ws_port,
            )
            await asyncio.Future()

    async def _handle_connection(self, websocket: websockets.ServerConnection) -> None:
        logger.info("Client connected: %s", websocket.remote_address)
        try:
            async for payload in websocket:
                try:
                    envelope = self._decode_payload(payload)
                    await self._pipeline.process_frame(envelope)
                except Exception:
                    logger.exception("Failed to process incoming payload")
        except websockets.ConnectionClosed:
            logger.info("Client disconnected: %s", websocket.remote_address)

    def _decode_payload(self, payload: bytes | str) -> FrameEnvelope:
        received_at = datetime.now(tz=timezone.utc)
        if isinstance(payload, bytes):
            return FrameEnvelope(
                image_bytes=payload,
                source="binary",
                received_at=received_at,
            )

        parsed = self._parse_text_payload(payload)
        image_value = parsed.get("image_base64") or parsed.get("image") or parsed.get("data")
        if not isinstance(image_value, str):
            raise ValueError("Text WebSocket payload must include image_base64/image/data")

        image_bytes = base64.b64decode(self._strip_data_uri_prefix(image_value), validate=True)
        source = str(parsed.get("source") or "json")
        message_id = parsed.get("message_id")
        return FrameEnvelope(
            image_bytes=image_bytes,
            source=source,
            received_at=received_at,
            message_id=str(message_id) if message_id is not None else None,
        )

    def _parse_text_payload(self, payload: str) -> dict[str, Any]:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return {"image_base64": payload, "source": "base64"}

        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str):
            return {"image_base64": parsed, "source": "json-string"}
        raise ValueError("Unsupported text payload structure")

    def _strip_data_uri_prefix(self, value: str) -> str:
        if value.startswith("data:") and "," in value:
            _, _, body = value.partition(",")
            return body
        return value
