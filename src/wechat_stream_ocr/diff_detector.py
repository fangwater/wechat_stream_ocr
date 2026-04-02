from __future__ import annotations

import numpy as np
from PIL import Image

from .config import AppConfig
from .models import DiffResult


class DiffDetector:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def compare(
        self,
        previous_frame: Image.Image | None,
        current_frame: Image.Image,
    ) -> DiffResult:
        if previous_frame is None:
            return DiffResult(
                has_new_messages=False,
                changed_ratio=0.0,
                mean_delta=0.0,
                changed_bbox=None,
            )

        previous_roi = self._extract_chat_roi(previous_frame)
        current_roi = self._extract_chat_roi(current_frame)
        if previous_roi.size != current_roi.size:
            previous_roi = previous_roi.resize(current_roi.size)

        previous_array = np.asarray(previous_roi.convert("L"), dtype=np.int16)
        current_array = np.asarray(current_roi.convert("L"), dtype=np.int16)
        delta = np.abs(current_array - previous_array)
        changed_mask = delta >= self._config.diff_pixel_threshold

        changed_ratio = float(changed_mask.mean())
        mean_delta = float(delta.mean())
        has_new_messages = (
            changed_ratio >= self._config.diff_min_changed_ratio
            and mean_delta >= self._config.diff_min_mean_delta
        )
        changed_bbox = None
        if has_new_messages and changed_mask.any():
            rows, cols = np.nonzero(changed_mask)
            changed_bbox = (
                int(cols.min()),
                int(rows.min()),
                int(cols.max()) + 1,
                int(rows.max()) + 1,
            )
        return DiffResult(
            has_new_messages=has_new_messages,
            changed_ratio=changed_ratio,
            mean_delta=mean_delta,
            changed_bbox=changed_bbox,
        )

    def _extract_chat_roi(self, image: Image.Image) -> Image.Image:
        left, top, right, bottom = self._config.roi_box(*image.size)
        return image.crop((left, top, right, bottom))
