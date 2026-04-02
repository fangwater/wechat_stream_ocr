from __future__ import annotations

import unittest
from unittest.mock import patch

from wechat_stream_ocr.config import AppConfig
from wechat_stream_ocr.ocr import _resolve_paddle_model_names, _resolve_paddle_runtime_device


class PaddleDeviceSelectionTests(unittest.TestCase):
    def test_auto_device_prefers_gpu_when_runtime_is_available(self) -> None:
        config = AppConfig(ocr_backend="paddleocr", paddle_device="auto")
        with patch("wechat_stream_ocr.ocr._gpu_runtime_available", return_value=True):
            self.assertEqual(_resolve_paddle_runtime_device(config), "gpu")

    def test_auto_device_falls_back_to_cpu_when_runtime_is_unavailable(self) -> None:
        config = AppConfig(ocr_backend="paddleocr", paddle_device="auto")
        with patch("wechat_stream_ocr.ocr._gpu_runtime_available", return_value=False):
            self.assertEqual(_resolve_paddle_runtime_device(config), "cpu")

    def test_explicit_gpu_requires_available_runtime(self) -> None:
        config = AppConfig(ocr_backend="paddleocr", paddle_device="gpu")
        with patch("wechat_stream_ocr.ocr._gpu_runtime_available", return_value=False):
            with self.assertRaises(RuntimeError):
                _resolve_paddle_runtime_device(config)

    def test_cpu_mode_uses_mobile_models_by_default(self) -> None:
        config = AppConfig(
            ocr_backend="paddleocr",
            paddle_device="cpu",
            paddle_cpu_text_detection_model_name="PP-OCRv5_mobile_det",
            paddle_cpu_text_recognition_model_name="PP-OCRv5_mobile_rec",
            paddle_gpu_text_detection_model_name="PP-OCRv5_server_det",
            paddle_gpu_text_recognition_model_name="PP-OCRv5_server_rec",
        )
        self.assertEqual(
            _resolve_paddle_model_names(config, "cpu"),
            ("PP-OCRv5_mobile_det", "PP-OCRv5_mobile_rec"),
        )

    def test_gpu_mode_uses_server_models_by_default(self) -> None:
        config = AppConfig(
            ocr_backend="paddleocr",
            paddle_device="gpu",
            paddle_cpu_text_detection_model_name="PP-OCRv5_mobile_det",
            paddle_cpu_text_recognition_model_name="PP-OCRv5_mobile_rec",
            paddle_gpu_text_detection_model_name="PP-OCRv5_server_det",
            paddle_gpu_text_recognition_model_name="PP-OCRv5_server_rec",
        )
        self.assertEqual(
            _resolve_paddle_model_names(config, "gpu"),
            ("PP-OCRv5_server_det", "PP-OCRv5_server_rec"),
        )

    def test_explicit_model_override_wins_over_device_defaults(self) -> None:
        config = AppConfig(
            ocr_backend="paddleocr",
            paddle_device="gpu",
            paddle_text_detection_model_name="custom_det",
            paddle_text_recognition_model_name="custom_rec",
        )
        self.assertEqual(
            _resolve_paddle_model_names(config, "gpu"),
            ("custom_det", "custom_rec"),
        )


if __name__ == "__main__":
    unittest.main()
