from __future__ import annotations

import asyncio
import contextlib
import socket
import unittest
from io import BytesIO

from PIL import Image
import websockets
import zmq
import zmq.asyncio

from wechat_stream_ocr.config import AppConfig
from wechat_stream_ocr.ocr import build_ocr_engine
from wechat_stream_ocr.pipeline import ProcessingPipeline
from wechat_stream_ocr.publisher_zmq import ZmqPublisher
from wechat_stream_ocr.ws_server import WebSocketImageServer


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _png_bytes(color: str) -> bytes:
    image = Image.new("RGB", (120, 160), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class EndToEndPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_to_zmq_pipeline_with_mock_ocr(self) -> None:
        ws_port = _free_tcp_port()
        zmq_port = _free_tcp_port()
        topic = "wechat.chat"
        config = AppConfig(
            ws_host="127.0.0.1",
            ws_port=ws_port,
            zmq_bind=f"tcp://127.0.0.1:{zmq_port}",
            zmq_topic=topic,
            ocr_backend="mock",
            mock_ocr_lines="[张三] [2026-03-30 13:45:00] 今天下午开会",
            diff_pixel_threshold=10,
            diff_min_changed_ratio=0.0001,
            diff_min_mean_delta=0.05,
            roi_left=0.0,
            roi_top=0.0,
            roi_right=1.0,
            roi_bottom=1.0,
        )
        publisher = ZmqPublisher(config.zmq_bind, config.zmq_topic)
        pipeline = ProcessingPipeline(
            config=config,
            ocr_engine=build_ocr_engine(config),
            publisher=publisher,
        )
        server = WebSocketImageServer(config=config, pipeline=pipeline)

        zmq_context = zmq.asyncio.Context.instance()
        subscriber = zmq_context.socket(zmq.SUB)
        subscriber.setsockopt_string(zmq.SUBSCRIBE, topic)
        subscriber.connect(config.zmq_bind.replace("*", "127.0.0.1"))

        server_task = asyncio.create_task(server.serve())
        try:
            await asyncio.sleep(0.2)
            async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as websocket:
                await websocket.send(_png_bytes("white"))
                await websocket.send(_png_bytes("black"))

            await asyncio.sleep(0.2)
            received_topic, payload = await asyncio.wait_for(
                subscriber.recv_multipart(),
                timeout=5.0,
            )
        finally:
            subscriber.close(0)
            server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await server_task
            await pipeline.close()

        self.assertEqual(received_topic.decode("utf-8"), topic)
        self.assertEqual(
            payload.decode("utf-8"),
            "[张三] [2026-03-30 13:45:00] 今天下午开会",
        )


if __name__ == "__main__":
    unittest.main()
