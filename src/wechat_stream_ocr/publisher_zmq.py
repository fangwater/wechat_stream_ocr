from __future__ import annotations

import zmq.asyncio

from .models import ChatMessage


class ZmqPublisher:
    def __init__(self, bind_address: str, topic: str) -> None:
        self._context = zmq.asyncio.Context.instance()
        self._socket = self._context.socket(zmq.PUB)
        self._socket.bind(bind_address)
        self._topic = topic.encode("utf-8") if topic else b""

    async def publish(self, message: ChatMessage) -> None:
        payload = message.format_text().encode("utf-8")
        if self._topic:
            await self._socket.send_multipart([self._topic, payload])
            return
        await self._socket.send(payload)

    async def close(self) -> None:
        self._socket.close(0)
