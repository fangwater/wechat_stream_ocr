from __future__ import annotations

import argparse
import asyncio
import contextlib
import socket
from pathlib import Path

import websockets
import zmq
import zmq.asyncio

from wechat_stream_ocr.config import AppConfig
from wechat_stream_ocr.ocr import build_ocr_engine
from wechat_stream_ocr.pipeline import ProcessingPipeline
from wechat_stream_ocr.publisher_zmq import ZmqPublisher
from wechat_stream_ocr.ws_server import WebSocketImageServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a PaddleOCR end-to-end smoke test")
    parser.add_argument("--before", required=True, help="Path to the baseline frame")
    parser.add_argument("--after", required=True, help="Path to the updated frame")
    parser.add_argument("--ocr-language", default="en", help="PaddleOCR language code")
    parser.add_argument("--timeout", type=float, default=90.0, help="Seconds to wait for the first ZMQ output")
    return parser


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def run_smoke_test(
    before_path: Path,
    after_path: Path,
    ocr_language: str,
    timeout: float,
) -> list[str]:
    ws_port = find_free_port()
    zmq_port = find_free_port()
    topic = "wechat.chat"
    config = AppConfig(
        ws_host="127.0.0.1",
        ws_port=ws_port,
        zmq_bind=f"tcp://127.0.0.1:{zmq_port}",
        zmq_topic=topic,
        ocr_backend="paddleocr",
        ocr_language=ocr_language,
        ocr_min_confidence=0.1,
        paddle_device="auto",
        paddle_use_doc_orientation_classify=False,
        paddle_use_doc_unwarping=False,
        paddle_use_textline_orientation=False,
        paddle_enable_mkldnn=False,
        paddle_enable_hpi=False,
        paddle_cpu_threads=1,
        diff_pixel_threshold=10,
        diff_min_changed_ratio=0.0001,
        diff_min_mean_delta=0.05,
        roi_left=0.20,
        roi_top=0.16,
        roi_right=0.93,
        roi_bottom=0.92,
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
    subscriber.connect(config.zmq_bind)

    server_task = asyncio.create_task(server.serve())
    try:
        await asyncio.sleep(0.8)
        async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as websocket:
            await websocket.send(before_path.read_bytes())
            await websocket.send(after_path.read_bytes())
        received_topic, payload = await asyncio.wait_for(
            subscriber.recv_multipart(),
            timeout=timeout,
        )
        if received_topic.decode("utf-8") != topic:
            raise RuntimeError(f"Unexpected topic: {received_topic!r}")
        messages = [payload.decode("utf-8")]
        while True:
            try:
                _, next_payload = await asyncio.wait_for(
                    subscriber.recv_multipart(),
                    timeout=1.0,
                )
            except TimeoutError:
                break
            messages.append(next_payload.decode("utf-8"))
        return messages
    finally:
        subscriber.close(0)
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server_task
        await pipeline.close()


def main() -> None:
    args = build_parser().parse_args()
    results = asyncio.run(
        run_smoke_test(
            before_path=Path(args.before),
            after_path=Path(args.after),
            ocr_language=args.ocr_language,
            timeout=args.timeout,
        )
    )
    for line in results:
        print(line)


if __name__ == "__main__":
    main()
