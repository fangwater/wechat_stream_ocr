from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import replace

from .config import AppConfig
from .ocr import build_ocr_engine
from .pipeline import ProcessingPipeline
from .publisher_zmq import ZmqPublisher
from .ws_server import WebSocketImageServer


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WeChat screenshot OCR streamer")
    parser.add_argument("--ws-host", help="WebSocket bind host")
    parser.add_argument("--ws-port", type=int, help="WebSocket bind port")
    parser.add_argument("--zmq-bind", help="ZeroMQ PUB bind address")
    parser.add_argument("--zmq-topic", help="ZeroMQ topic name")
    parser.add_argument("--ocr-backend", help="OCR backend name: stub, mock, or paddleocr")
    parser.add_argument("--log-level", help="Logging level")
    return parser


async def run(config: AppConfig) -> None:
    publisher = ZmqPublisher(config.zmq_bind, config.zmq_topic)
    pipeline = ProcessingPipeline(
        config=config,
        ocr_engine=build_ocr_engine(config),
        publisher=publisher,
    )
    server = WebSocketImageServer(config=config, pipeline=pipeline)
    try:
        await server.serve()
    finally:
        await pipeline.close()


def main() -> None:
    base_config = AppConfig.from_env()
    args = build_arg_parser().parse_args()
    config = replace(
        base_config,
        ws_host=args.ws_host or base_config.ws_host,
        ws_port=args.ws_port or base_config.ws_port,
        zmq_bind=args.zmq_bind or base_config.zmq_bind,
        zmq_topic=args.zmq_topic or base_config.zmq_topic,
        ocr_backend=args.ocr_backend or base_config.ocr_backend,
        log_level=(args.log_level or base_config.log_level).upper(),
    )

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        asyncio.run(run(config))
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutdown requested by user")


if __name__ == "__main__":
    main()
