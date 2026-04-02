from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Protocol

from PIL import Image

from .config import AppConfig
from .models import OcrLine

logger = logging.getLogger(__name__)


class OcrEngine(Protocol):
    def extract_lines(self, image: Image.Image) -> list[OcrLine]:
        ...


class StubOcrEngine:
    def extract_lines(self, image: Image.Image) -> list[OcrLine]:
        logger.debug("OCR backend is stub; skipping frame with size=%s", image.size)
        return []


class MockOcrEngine:
    def __init__(self, config: AppConfig) -> None:
        self._lines = [
            OcrLine(text=line.strip(), confidence=1.0)
            for line in config.mock_ocr_lines.splitlines()
            if line.strip()
        ]

    def extract_lines(self, image: Image.Image) -> list[OcrLine]:
        logger.debug(
            "OCR backend is mock; returning %s configured lines for frame size=%s",
            len(self._lines),
            image.size,
        )
        return list(self._lines)


class PaddleOcrEngine:
    def __init__(self, config: AppConfig) -> None:
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        os.environ.setdefault("FLAGS_enable_pir_api", "0")
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                "paddleocr backend could not be imported. "
                "This can mean missing Python packages or missing native libraries such as libGL. "
                f"Original error: {exc}"
            ) from exc

        self._min_confidence = config.ocr_min_confidence
        self._use_textline_orientation = config.paddle_use_textline_orientation
        device = _resolve_paddle_runtime_device(config)
        detection_model_name, recognition_model_name = _resolve_paddle_model_names(config, device)
        self._ocr = PaddleOCR(
            lang=config.ocr_language,
            text_detection_model_name=detection_model_name,
            text_recognition_model_name=recognition_model_name,
            use_doc_orientation_classify=config.paddle_use_doc_orientation_classify,
            use_doc_unwarping=config.paddle_use_doc_unwarping,
            use_textline_orientation=config.paddle_use_textline_orientation,
            device=device,
            text_rec_score_thresh=config.ocr_min_confidence,
            enable_mkldnn=config.paddle_enable_mkldnn,
            enable_hpi=config.paddle_enable_hpi,
            cpu_threads=config.paddle_cpu_threads,
        )
        logger.info(
            "Initialized PaddleOCR with device=%s requested_device=%s det_model=%s rec_model=%s",
            device,
            config.paddle_device,
            detection_model_name,
            recognition_model_name,
        )

    def extract_lines(self, image: Image.Image) -> list[OcrLine]:
        import numpy as np

        result = self._ocr.predict(
            np.asarray(image),
            use_textline_orientation=self._use_textline_orientation,
            text_rec_score_thresh=self._min_confidence,
        )
        lines: list[OcrLine] = []
        for batch in result or []:
            lines.extend(self._parse_batch(batch))
        lines.sort(key=_ocr_line_sort_key)
        return lines

    def _parse_batch(self, batch: object) -> list[OcrLine]:
        if not isinstance(batch, dict):
            raise RuntimeError(f"Unexpected PaddleOCR 3.x batch payload: {type(batch)!r}")

        texts = batch.get("rec_texts") or []
        scores = batch.get("rec_scores") or []
        polys = batch.get("rec_polys") or batch.get("dt_polys") or []
        parsed_lines: list[OcrLine] = []
        for text, confidence, poly in zip(texts, scores, polys):
            normalized_text = str(text).strip()
            normalized_confidence = float(confidence)
            if not normalized_text or normalized_confidence < self._min_confidence:
                continue
            parsed_lines.append(
                OcrLine(
                    text=normalized_text,
                    confidence=normalized_confidence,
                    bbox=_extract_bbox(poly),
                )
            )
        return parsed_lines


def _extract_bbox(raw_box: object) -> tuple[float, float, float, float] | None:
    if not isinstance(raw_box, (list, tuple)) or not raw_box:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for point in raw_box:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        xs.append(float(point[0]))
        ys.append(float(point[1]))
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _ocr_line_sort_key(line: OcrLine) -> tuple[float, float]:
    if line.bbox is None:
        return float("inf"), float("inf")
    left, top, _, _ = line.bbox
    return top, left


def _resolve_paddle_runtime_device(config: AppConfig) -> str:
    requested_device = config.paddle_device.strip().lower()
    if requested_device == "cpu":
        return "cpu"
    if requested_device == "gpu":
        if _gpu_runtime_available():
            return "gpu"
        raise RuntimeError(
            "WSOCR_PADDLE_DEVICE=gpu was requested, but no usable Paddle CUDA runtime was detected"
        )
    if requested_device == "auto":
        return "gpu" if _gpu_runtime_available() else "cpu"
    raise ValueError(f"Unsupported Paddle device mode: {config.paddle_device}")


def _resolve_paddle_model_names(config: AppConfig, device: str) -> tuple[str, str]:
    detection_model_name = config.paddle_text_detection_model_name
    recognition_model_name = config.paddle_text_recognition_model_name
    if detection_model_name and recognition_model_name:
        return detection_model_name, recognition_model_name

    if device == "gpu":
        return (
            detection_model_name or config.paddle_gpu_text_detection_model_name,
            recognition_model_name or config.paddle_gpu_text_recognition_model_name,
        )

    return (
        detection_model_name or config.paddle_cpu_text_detection_model_name,
        recognition_model_name or config.paddle_cpu_text_recognition_model_name,
    )


def _gpu_runtime_available() -> bool:
    if not _nvidia_smi_reports_gpu():
        logger.info("GPU auto-detection: nvidia-smi did not report a usable NVIDIA GPU; using CPU")
        return False

    try:
        import paddle
    except ImportError:
        logger.info("GPU auto-detection: paddle package is unavailable; using CPU")
        return False

    try:
        is_compiled_with_cuda = bool(paddle.device.is_compiled_with_cuda())
    except Exception as exc:
        logger.warning("GPU auto-detection: failed to query Paddle CUDA support: %s", exc)
        return False

    if not is_compiled_with_cuda:
        logger.info("GPU auto-detection: installed Paddle is not compiled with CUDA; using CPU")
        return False

    try:
        gpu_count = int(paddle.device.cuda.device_count())
    except Exception as exc:
        logger.warning("GPU auto-detection: failed to query Paddle GPU count: %s", exc)
        return False

    if gpu_count <= 0:
        logger.info("GPU auto-detection: Paddle reported zero CUDA devices; using CPU")
        return False

    logger.info("GPU auto-detection: detected %s CUDA device(s); using GPU", gpu_count)
    return True


def _nvidia_smi_reports_gpu() -> bool:
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        completed = subprocess.run(
            ["nvidia-smi", "-L"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("GPU auto-detection: failed to execute nvidia-smi: %s", exc)
        return False
    return completed.returncode == 0 and bool(completed.stdout.strip())


def build_ocr_engine(config: AppConfig) -> OcrEngine:
    normalized_backend = config.ocr_backend.strip().lower()
    if normalized_backend == "stub":
        return StubOcrEngine()
    if normalized_backend == "mock":
        return MockOcrEngine(config)
    if normalized_backend == "paddleocr":
        return PaddleOcrEngine(config)
    raise ValueError(f"Unsupported OCR backend: {config.ocr_backend}")
