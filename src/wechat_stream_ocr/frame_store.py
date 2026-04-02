from __future__ import annotations

from PIL import Image


class FrameStore:
    def __init__(self) -> None:
        self._previous_frame: Image.Image | None = None

    def swap(self, current_frame: Image.Image) -> Image.Image | None:
        previous_frame = self._previous_frame
        self._previous_frame = current_frame.copy()
        return previous_frame
