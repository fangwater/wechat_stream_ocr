from __future__ import annotations

import argparse
import asyncio
import contextlib
import socket
import statistics
import time
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
import websockets
import zmq
import zmq.asyncio

from wechat_stream_ocr.config import AppConfig
from wechat_stream_ocr.ocr import build_ocr_engine
from wechat_stream_ocr.pipeline import ProcessingPipeline
from wechat_stream_ocr.publisher_zmq import ZmqPublisher
from wechat_stream_ocr.ws_server import WebSocketImageServer


DEFAULT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark PaddleOCR with a burst of synthetic frames")
    parser.add_argument("--frames", type=int, default=20, help="Total frames to send")
    parser.add_argument("--interval-ms", type=int, default=500, help="Interval between frames in milliseconds")
    parser.add_argument("--ocr-language", default="en", help="PaddleOCR language code")
    parser.add_argument("--timeout", type=float, default=180.0, help="Seconds to wait for final ZMQ output")
    return parser


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def render_frame(message_count: int) -> bytes:
    width = 1440
    height = 900
    image = Image.new("RGB", (width, height), "#f5f5f5")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(DEFAULT_FONT, 42)
    bubble_font = ImageFont.truetype(DEFAULT_FONT, 36)

    draw.rectangle((320, 80, 1320, 820), fill="white")
    draw.rectangle((320, 80, 1320, 140), fill="#ededed")
    draw.text((360, 94), "Synthetic Chat Window", fill="#202020", font=title_font)

    top = 180
    messages = ["Alice 2026-03-30 13:40:00 status ready"]
    for index in range(max(0, message_count - 1)):
        total_minutes = 13 * 60 + 41 + index
        hour, minute = divmod(total_minutes, 60)
        messages.append(f"Alice 2026-03-30 {hour:02d}:{minute:02d}:00 task {index + 1}")

    visible_messages = messages[-5:]
    for index, text in enumerate(visible_messages):
        bubble_top = top + index * 120
        draw.rounded_rectangle((420, bubble_top, 1220, bubble_top + 84), radius=18, fill="#dcf8c6")
        draw.text((460, bubble_top + 22), text, fill="#101010", font=bubble_font)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def collect_messages(subscriber: zmq.asyncio.Socket, stop_event: asyncio.Event, storage: list[tuple[float, str]]) -> None:
    while True:
        if stop_event.is_set():
            try:
                topic, payload = await asyncio.wait_for(subscriber.recv_multipart(), timeout=1.0)
            except TimeoutError:
                return
        else:
            topic, payload = await subscriber.recv_multipart()
        _ = topic
        storage.append((time.monotonic(), payload.decode("utf-8")))


async def run_benchmark(frame_count: int, interval_ms: int, ocr_language: str, timeout: float) -> dict[str, object]:
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
        ocr_crop_padding=16,
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
    received_messages: list[tuple[float, str]] = []
    stop_event = asyncio.Event()
    collector_task = asyncio.create_task(collect_messages(subscriber, stop_event, received_messages))
    send_times: list[float] = []

    try:
        await asyncio.sleep(0.8)
        async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as websocket:
            start_time = time.monotonic()
            for frame_index in range(frame_count):
                send_times.append(time.monotonic())
                await websocket.send(render_frame(frame_index + 1))
                next_deadline = start_time + (frame_index + 1) * (interval_ms / 1000.0)
                await asyncio.sleep(max(0.0, next_deadline - time.monotonic()))

        expected_publishes = frame_count - 1
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(received_messages) >= expected_publishes:
                break
            await asyncio.sleep(0.5)
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(collector_task, timeout=5.0)
        except TimeoutError:
            collector_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await collector_task
        subscriber.close(0)
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server_task
        await pipeline.close()

    expected_publishes = frame_count - 1
    latencies_ms: list[float] = []
    for sent_at, (received_at, _) in zip(send_times[1:], received_messages):
        latencies_ms.append((received_at - sent_at) * 1000.0)

    total_duration_ms = 0.0
    if send_times and received_messages:
        total_duration_ms = (received_messages[-1][0] - send_times[0]) * 1000.0

    return {
        "frames_sent": frame_count,
        "interval_ms": interval_ms,
        "messages_received": [payload for _, payload in received_messages],
        "received_count": len(received_messages),
        "expected_publish_count": expected_publishes,
        "latencies_ms": latencies_ms,
        "avg_latency_ms": statistics.mean(latencies_ms) if latencies_ms else None,
        "max_latency_ms": max(latencies_ms) if latencies_ms else None,
        "total_duration_ms": total_duration_ms,
    }


def main() -> None:
    args = build_parser().parse_args()
    result = asyncio.run(
        run_benchmark(
            frame_count=args.frames,
            interval_ms=args.interval_ms,
            ocr_language=args.ocr_language,
            timeout=args.timeout,
        )
    )

    print(f"frames_sent={result['frames_sent']}")
    print(f"interval_ms={result['interval_ms']}")
    print(f"expected_publish_count={result['expected_publish_count']}")
    print(f"received_count={result['received_count']}")
    print(f"avg_latency_ms={result['avg_latency_ms']}")
    print(f"max_latency_ms={result['max_latency_ms']}")
    print(f"total_duration_ms={result['total_duration_ms']}")
    print("messages:")
    for message in result["messages_received"]:
        print(message)


if __name__ == "__main__":
    main()
