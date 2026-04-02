from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_optional_str(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


@dataclass(frozen=True, slots=True)
class AppConfig:
    ws_host: str = "0.0.0.0"
    ws_port: int = 8765
    max_payload_bytes: int = 8 * 1024 * 1024
    zmq_bind: str = "tcp://127.0.0.1:5556"
    zmq_topic: str = "wechat.chat"
    diff_pixel_threshold: int = 18
    diff_min_changed_ratio: float = 0.003
    diff_min_mean_delta: float = 1.5
    roi_left: float = 0.0
    roi_top: float = 0.0
    roi_right: float = 1.0
    roi_bottom: float = 1.0
    incremental_scan_width: int = 96
    incremental_scan_height: int = 256
    incremental_max_shift_ratio: float = 0.45
    incremental_min_overlap_ratio: float = 0.35
    incremental_score_ratio_threshold: float = 0.72
    incremental_min_shift_rows: int = 8
    ocr_backend: str = "stub"
    ocr_language: str = "ch"
    ocr_min_confidence: float = 0.60
    paddle_text_detection_model_name: str | None = None
    paddle_text_recognition_model_name: str | None = None
    paddle_cpu_text_detection_model_name: str = "PP-OCRv5_mobile_det"
    paddle_cpu_text_recognition_model_name: str = "PP-OCRv5_mobile_rec"
    paddle_gpu_text_detection_model_name: str = "PP-OCRv5_server_det"
    paddle_gpu_text_recognition_model_name: str = "PP-OCRv5_server_rec"
    paddle_use_doc_orientation_classify: bool = False
    paddle_use_doc_unwarping: bool = False
    paddle_use_textline_orientation: bool = False
    paddle_device: str = "auto"
    paddle_use_gpu: bool = False
    paddle_enable_mkldnn: bool = False
    paddle_enable_hpi: bool = False
    paddle_cpu_threads: int = 1
    ocr_crop_padding: int = 16
    segment_background_margin: int = 18
    segment_color_distance_threshold: float = 22.0
    segment_row_active_ratio: float = 0.020
    segment_min_band_gap: int = 10
    segment_merge_gap: int = 22
    segment_min_height: int = 24
    segment_padding_y: int = 12
    segment_hash_distance: int = 6
    mock_ocr_lines: str = "[mock] [2000-01-01 00:00:00] smoke test message"
    dedupe_cache_size: int = 2048
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "AppConfig":
        defaults = cls()
        paddle_device = cls._resolve_paddle_device(defaults)
        return cls(
            ws_host=os.getenv("WSOCR_WS_HOST", defaults.ws_host),
            ws_port=_env_int("WSOCR_WS_PORT", defaults.ws_port),
            max_payload_bytes=_env_int("WSOCR_MAX_PAYLOAD_BYTES", defaults.max_payload_bytes),
            zmq_bind=os.getenv("WSOCR_ZMQ_BIND", defaults.zmq_bind),
            zmq_topic=os.getenv("WSOCR_ZMQ_TOPIC", defaults.zmq_topic),
            diff_pixel_threshold=_env_int("WSOCR_DIFF_PIXEL_THRESHOLD", defaults.diff_pixel_threshold),
            diff_min_changed_ratio=_env_float(
                "WSOCR_DIFF_MIN_CHANGED_RATIO",
                defaults.diff_min_changed_ratio,
            ),
            diff_min_mean_delta=_env_float(
                "WSOCR_DIFF_MIN_MEAN_DELTA",
                defaults.diff_min_mean_delta,
            ),
            roi_left=_env_float("WSOCR_ROI_LEFT", defaults.roi_left),
            roi_top=_env_float("WSOCR_ROI_TOP", defaults.roi_top),
            roi_right=_env_float("WSOCR_ROI_RIGHT", defaults.roi_right),
            roi_bottom=_env_float("WSOCR_ROI_BOTTOM", defaults.roi_bottom),
            incremental_scan_width=_env_int(
                "WSOCR_INCREMENTAL_SCAN_WIDTH",
                defaults.incremental_scan_width,
            ),
            incremental_scan_height=_env_int(
                "WSOCR_INCREMENTAL_SCAN_HEIGHT",
                defaults.incremental_scan_height,
            ),
            incremental_max_shift_ratio=_env_float(
                "WSOCR_INCREMENTAL_MAX_SHIFT_RATIO",
                defaults.incremental_max_shift_ratio,
            ),
            incremental_min_overlap_ratio=_env_float(
                "WSOCR_INCREMENTAL_MIN_OVERLAP_RATIO",
                defaults.incremental_min_overlap_ratio,
            ),
            incremental_score_ratio_threshold=_env_float(
                "WSOCR_INCREMENTAL_SCORE_RATIO_THRESHOLD",
                defaults.incremental_score_ratio_threshold,
            ),
            incremental_min_shift_rows=_env_int(
                "WSOCR_INCREMENTAL_MIN_SHIFT_ROWS",
                defaults.incremental_min_shift_rows,
            ),
            ocr_backend=os.getenv("WSOCR_OCR_BACKEND", defaults.ocr_backend),
            ocr_language=os.getenv("WSOCR_OCR_LANGUAGE", defaults.ocr_language),
            ocr_min_confidence=_env_float(
                "WSOCR_OCR_MIN_CONFIDENCE",
                defaults.ocr_min_confidence,
            ),
            paddle_text_detection_model_name=_env_optional_str(
                "WSOCR_PADDLE_TEXT_DETECTION_MODEL_NAME"
            ),
            paddle_text_recognition_model_name=_env_optional_str(
                "WSOCR_PADDLE_TEXT_RECOGNITION_MODEL_NAME"
            ),
            paddle_cpu_text_detection_model_name=os.getenv(
                "WSOCR_PADDLE_CPU_TEXT_DETECTION_MODEL_NAME",
                defaults.paddle_cpu_text_detection_model_name,
            ),
            paddle_cpu_text_recognition_model_name=os.getenv(
                "WSOCR_PADDLE_CPU_TEXT_RECOGNITION_MODEL_NAME",
                defaults.paddle_cpu_text_recognition_model_name,
            ),
            paddle_gpu_text_detection_model_name=os.getenv(
                "WSOCR_PADDLE_GPU_TEXT_DETECTION_MODEL_NAME",
                defaults.paddle_gpu_text_detection_model_name,
            ),
            paddle_gpu_text_recognition_model_name=os.getenv(
                "WSOCR_PADDLE_GPU_TEXT_RECOGNITION_MODEL_NAME",
                defaults.paddle_gpu_text_recognition_model_name,
            ),
            paddle_use_doc_orientation_classify=os.getenv(
                "WSOCR_PADDLE_USE_DOC_ORIENTATION_CLASSIFY",
                str(defaults.paddle_use_doc_orientation_classify),
            ).lower()
            in {"1", "true", "yes", "on"},
            paddle_use_doc_unwarping=os.getenv(
                "WSOCR_PADDLE_USE_DOC_UNWARPING",
                str(defaults.paddle_use_doc_unwarping),
            ).lower()
            in {"1", "true", "yes", "on"},
            paddle_use_textline_orientation=os.getenv(
                "WSOCR_PADDLE_USE_TEXTLINE_ORIENTATION",
                str(defaults.paddle_use_textline_orientation),
            ).lower()
            in {"1", "true", "yes", "on"},
            paddle_device=paddle_device,
            paddle_use_gpu=paddle_device == "gpu",
            paddle_enable_mkldnn=os.getenv(
                "WSOCR_PADDLE_ENABLE_MKLDNN",
                str(defaults.paddle_enable_mkldnn),
            ).lower()
            in {"1", "true", "yes", "on"},
            paddle_enable_hpi=os.getenv(
                "WSOCR_PADDLE_ENABLE_HPI",
                str(defaults.paddle_enable_hpi),
            ).lower()
            in {"1", "true", "yes", "on"},
            paddle_cpu_threads=_env_int(
                "WSOCR_PADDLE_CPU_THREADS",
                defaults.paddle_cpu_threads,
            ),
            ocr_crop_padding=_env_int(
                "WSOCR_OCR_CROP_PADDING",
                defaults.ocr_crop_padding,
            ),
            segment_background_margin=_env_int(
                "WSOCR_SEGMENT_BACKGROUND_MARGIN",
                defaults.segment_background_margin,
            ),
            segment_color_distance_threshold=_env_float(
                "WSOCR_SEGMENT_COLOR_DISTANCE_THRESHOLD",
                defaults.segment_color_distance_threshold,
            ),
            segment_row_active_ratio=_env_float(
                "WSOCR_SEGMENT_ROW_ACTIVE_RATIO",
                defaults.segment_row_active_ratio,
            ),
            segment_min_band_gap=_env_int(
                "WSOCR_SEGMENT_MIN_BAND_GAP",
                defaults.segment_min_band_gap,
            ),
            segment_merge_gap=_env_int(
                "WSOCR_SEGMENT_MERGE_GAP",
                defaults.segment_merge_gap,
            ),
            segment_min_height=_env_int(
                "WSOCR_SEGMENT_MIN_HEIGHT",
                defaults.segment_min_height,
            ),
            segment_padding_y=_env_int(
                "WSOCR_SEGMENT_PADDING_Y",
                defaults.segment_padding_y,
            ),
            segment_hash_distance=_env_int(
                "WSOCR_SEGMENT_HASH_DISTANCE",
                defaults.segment_hash_distance,
            ),
            mock_ocr_lines=os.getenv("WSOCR_MOCK_OCR_LINES", defaults.mock_ocr_lines),
            dedupe_cache_size=_env_int("WSOCR_DEDUPE_CACHE_SIZE", defaults.dedupe_cache_size),
            log_level=os.getenv("WSOCR_LOG_LEVEL", defaults.log_level),
        )

    @staticmethod
    def _resolve_paddle_device(defaults: "AppConfig") -> str:
        configured = os.getenv("WSOCR_PADDLE_DEVICE")
        if configured is not None:
            normalized = configured.strip().lower()
        else:
            legacy_gpu_flag = os.getenv("WSOCR_PADDLE_USE_GPU")
            if legacy_gpu_flag is None:
                normalized = defaults.paddle_device
            else:
                normalized = "gpu" if _env_bool("WSOCR_PADDLE_USE_GPU", defaults.paddle_use_gpu) else "cpu"

        if normalized in {"auto", "cpu", "gpu"}:
            return normalized
        raise ValueError(
            "WSOCR_PADDLE_DEVICE must be one of: auto, cpu, gpu"
        )

    def roi_box(self, width: int, height: int) -> tuple[int, int, int, int]:
        left = int(width * _clamp(self.roi_left, 0.0, 0.99))
        top = int(height * _clamp(self.roi_top, 0.0, 0.99))
        right = int(width * _clamp(self.roi_right, 0.01, 1.0))
        bottom = int(height * _clamp(self.roi_bottom, 0.01, 1.0))
        if right <= left:
            right = min(width, left + 1)
        if bottom <= top:
            bottom = min(height, top + 1)
        return left, top, right, bottom
