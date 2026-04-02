from __future__ import annotations

import asyncio
import logging
from collections import deque
from io import BytesIO

import numpy as np
from PIL import Image, UnidentifiedImageError

from .config import AppConfig
from .diff_detector import DiffDetector
from .frame_store import FrameStore
from .message_filter import MessageFilter
from .message_parser import MessageParser
from .models import ChatMessage, FrameEnvelope
from .ocr import OcrEngine
from .publisher_zmq import ZmqPublisher

logger = logging.getLogger(__name__)


SegmentCrop = tuple[tuple[int, int, int, int], Image.Image]
SegmentObservation = tuple[int, tuple[str, ...]]


class ProcessingPipeline:
    def __init__(
        self,
        config: AppConfig,
        ocr_engine: OcrEngine,
        publisher: ZmqPublisher,
    ) -> None:
        self._config = config
        self._ocr_engine = ocr_engine
        self._publisher = publisher
        self._frame_store = FrameStore()
        self._diff_detector = DiffDetector(config)
        self._message_parser = MessageParser()
        self._message_filter = MessageFilter()
        self._recent_signatures: deque[str] = deque()
        self._signature_index: set[str] = set()
        self._recent_segment_observations: deque[SegmentObservation] = deque()

    async def process_frame(self, envelope: FrameEnvelope) -> list[ChatMessage]:
        logger.info(
            "Received frame source=%s bytes=%s message_id=%s",
            envelope.source,
            len(envelope.image_bytes),
            envelope.message_id,
        )
        current_frame = self._decode_image(envelope.image_bytes)
        logger.info("Decoded frame source=%s size=%s", envelope.source, current_frame.size)
        previous_frame = self._frame_store.swap(current_frame)
        chat_roi = self._extract_chat_roi(current_frame)
        if previous_frame is None:
            logger.info(
                "Stored initial frame from source=%s; segmenting full chat ROI",
                envelope.source,
            )
            return await self._run_ocr_and_publish(
                envelope=envelope,
                chat_roi=chat_roi,
                band_top=0,
                changed_bbox=None,
            )

        diff_result = self._diff_detector.compare(previous_frame, current_frame)
        if not diff_result.has_new_messages:
            logger.info(
                "No new messages detected source=%s changed_ratio=%.5f mean_delta=%.2f",
                envelope.source,
                diff_result.changed_ratio,
                diff_result.mean_delta,
            )
            return []

        logger.info(
            "Detected possible new chat content source=%s changed_ratio=%.5f mean_delta=%.2f changed_bbox=%s",
            envelope.source,
            diff_result.changed_ratio,
            diff_result.mean_delta,
            diff_result.changed_bbox,
        )
        band_top = self._find_incremental_band_top(
            previous_frame=previous_frame,
            current_frame=current_frame,
            fallback_bbox=diff_result.changed_bbox,
        )
        return await self._run_ocr_and_publish(
            envelope=envelope,
            chat_roi=chat_roi,
            band_top=band_top,
            changed_bbox=diff_result.changed_bbox,
        )

    async def close(self) -> None:
        await self._publisher.close()

    def _decode_image(self, image_bytes: bytes) -> Image.Image:
        try:
            with Image.open(BytesIO(image_bytes)) as image:
                image.load()
                return image.convert("RGB")
        except UnidentifiedImageError as exc:
            raise ValueError("Unsupported or corrupted image payload") from exc

    def _remember_signature(self, signature: str) -> bool:
        if signature in self._signature_index:
            return False

        self._recent_signatures.append(signature)
        self._signature_index.add(signature)
        while len(self._recent_signatures) > self._config.dedupe_cache_size:
            oldest_signature = self._recent_signatures.popleft()
            self._signature_index.discard(oldest_signature)
        return True

    def _extract_chat_roi(self, image: Image.Image) -> Image.Image:
        left, top, right, bottom = self._config.roi_box(*image.size)
        return image.crop((left, top, right, bottom))

    def _band_top_from_bbox(
        self,
        roi_height: int,
        changed_bbox: tuple[int, int, int, int] | None,
    ) -> int:
        if changed_bbox is None:
            return 0

        _, crop_top, _, _ = changed_bbox
        padding = max(self._config.ocr_crop_padding, 0)
        crop_top = max(0, crop_top - padding)
        return min(crop_top, max(0, roi_height - 1))

    def _find_incremental_band_top(
        self,
        previous_frame: Image.Image,
        current_frame: Image.Image,
        fallback_bbox: tuple[int, int, int, int] | None,
    ) -> int:
        previous_roi = self._extract_chat_roi(previous_frame)
        current_roi = self._extract_chat_roi(current_frame)
        if previous_roi.size != current_roi.size:
            previous_roi = previous_roi.resize(current_roi.size)

        scan_width = max(16, self._config.incremental_scan_width)
        scan_height = max(32, self._config.incremental_scan_height)
        previous_small = np.asarray(
            previous_roi.convert("L").resize((scan_width, scan_height)),
            dtype=np.int16,
        )
        current_small = np.asarray(
            current_roi.convert("L").resize((scan_width, scan_height)),
            dtype=np.int16,
        )

        baseline_score = float(np.mean(np.abs(current_small - previous_small)))
        max_shift = max(
            1,
            min(
                scan_height - 1,
                int(scan_height * self._config.incremental_max_shift_ratio),
            ),
        )
        min_overlap = max(8, int(scan_height * self._config.incremental_min_overlap_ratio))

        best_shift = 0
        best_score = baseline_score
        for shift in range(1, max_shift + 1):
            overlap = scan_height - shift
            if overlap < min_overlap:
                break
            shifted_score = float(
                np.mean(np.abs(current_small[:overlap] - previous_small[shift:]))
            )
            if shifted_score < best_score:
                best_shift = shift
                best_score = shifted_score

        fallback_top = self._band_top_from_bbox(current_roi.height, fallback_bbox)
        if best_shift < self._config.incremental_min_shift_rows:
            logger.info(
                "Incremental band fallback source=diff best_shift=%s baseline_score=%.2f best_score=%.2f fallback_top=%s",
                best_shift,
                baseline_score,
                best_score,
                fallback_top,
            )
            return fallback_top

        if baseline_score > 0:
            score_ratio = best_score / baseline_score
        else:
            score_ratio = 0.0
        if score_ratio > self._config.incremental_score_ratio_threshold:
            logger.info(
                "Incremental band fallback source=diff best_shift=%s baseline_score=%.2f best_score=%.2f score_ratio=%.3f fallback_top=%s",
                best_shift,
                baseline_score,
                best_score,
                score_ratio,
                fallback_top,
            )
            return fallback_top

        scaled_shift = int(round(best_shift * current_roi.height / scan_height))
        band_top = max(0, current_roi.height - scaled_shift - self._config.ocr_crop_padding)
        logger.info(
            "Incremental band estimated by shift best_shift=%s scaled_shift=%s baseline_score=%.2f best_score=%.2f score_ratio=%.3f band_top=%s",
            best_shift,
            scaled_shift,
            baseline_score,
            best_score,
            score_ratio,
            band_top,
        )
        return band_top

    async def _run_ocr_and_publish(
        self,
        envelope: FrameEnvelope,
        chat_roi: Image.Image,
        band_top: int,
        changed_bbox: tuple[int, int, int, int] | None,
    ) -> list[ChatMessage]:
        incremental_band = chat_roi.crop((0, band_top, chat_roi.width, chat_roi.height))
        logger.info(
            "Prepared incremental band source=%s size=%s band_top=%s changed_bbox=%s",
            envelope.source,
            incremental_band.size,
            band_top,
            changed_bbox,
        )
        segments = self._split_message_segments(incremental_band, band_top)
        logger.info(
            "Segmented chat band source=%s count=%s boxes=%s",
            envelope.source,
            len(segments),
            [segment_bbox for segment_bbox, _ in segments],
        )

        published_messages: list[ChatMessage] = []
        skipped_segments = 0
        for segment_bbox, segment_image in segments:
            segment_hash = self._compute_segment_hash(segment_image)
            has_similar_hash = self._has_similar_segment_hash(segment_hash)

            logger.info(
                "Running OCR on segment source=%s bbox=%s size=%s hash=%s similar_hash=%s",
                envelope.source,
                segment_bbox,
                segment_image.size,
                f"{segment_hash:016x}",
                has_similar_hash,
            )
            ocr_lines = await asyncio.to_thread(self._ocr_engine.extract_lines, segment_image)
            if not ocr_lines:
                logger.info(
                    "OCR returned no text lines source=%s segment_bbox=%s",
                    envelope.source,
                    segment_bbox,
                )
                continue
            logger.info(
                "OCR lines source=%s segment_bbox=%s count=%s lines=%s",
                envelope.source,
                segment_bbox,
                len(ocr_lines),
                [
                    {
                        "text": line.text,
                        "confidence": line.confidence,
                        "bbox": line.bbox,
                    }
                    for line in ocr_lines
                ],
            )

            parsed_messages = self._message_parser.parse(
                lines=ocr_lines,
                received_at=envelope.received_at,
                source=envelope.source,
            )
            logger.info(
                "Parsed messages source=%s segment_bbox=%s count=%s messages=%s",
                envelope.source,
                segment_bbox,
                len(parsed_messages),
                [message.format_text() for message in parsed_messages],
            )
            filtered_messages = self._message_filter.filter(parsed_messages)
            logger.info(
                "Filtered messages source=%s segment_bbox=%s count=%s messages=%s",
                envelope.source,
                segment_bbox,
                len(filtered_messages),
                [message.format_text() for message in filtered_messages],
            )
            normalized_messages = tuple(
                self._normalize_message_text(message) for message in filtered_messages
            )
            if normalized_messages and self._is_duplicate_segment_text(segment_hash, normalized_messages):
                skipped_segments += 1
                logger.info(
                    "Skipping duplicate segment after OCR source=%s segment_bbox=%s hash=%s messages=%s",
                    envelope.source,
                    segment_bbox,
                    f"{segment_hash:016x}",
                    list(normalized_messages),
                )
                continue

            for message in filtered_messages:
                if not self._remember_signature(message.signature()):
                    logger.debug("Skipping duplicate message: %s", message.format_text())
                    continue
                await self._publisher.publish(message)
                logger.info("Published message: %s", message.format_text())
                published_messages.append(message)
            if normalized_messages:
                self._remember_segment_observation(segment_hash, normalized_messages)

        logger.info(
            "Completed segment OCR source=%s published=%s skipped_similar_segments=%s",
            envelope.source,
            len(published_messages),
            skipped_segments,
        )

        return published_messages

    def _split_message_segments(
        self,
        image: Image.Image,
        offset_top: int,
    ) -> list[SegmentCrop]:
        rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
        if rgb.size == 0:
            return []

        background_color = self._estimate_background_color(rgb)
        color_delta = np.linalg.norm(rgb - background_color, axis=2)
        active_mask = color_delta >= self._config.segment_color_distance_threshold
        row_active_ratio = active_mask.mean(axis=1)
        active_rows = row_active_ratio >= self._config.segment_row_active_ratio

        segments: list[tuple[int, int]] = []
        start_row: int | None = None
        inactive_run = 0
        for row_index, is_active in enumerate(active_rows.tolist()):
            if is_active and start_row is None:
                start_row = row_index
                inactive_run = 0
                continue
            if is_active:
                inactive_run = 0
                continue
            if start_row is None:
                continue
            inactive_run += 1
            if inactive_run < self._config.segment_min_band_gap:
                continue
            segments.append((start_row, max(start_row + 1, row_index - inactive_run + 1)))
            start_row = None
            inactive_run = 0
        if start_row is not None:
            segments.append((start_row, image.height))

        merged_segments: list[tuple[int, int]] = []
        for start_row, end_row in segments:
            if not merged_segments:
                merged_segments.append((start_row, end_row))
                continue
            previous_start, previous_end = merged_segments[-1]
            if start_row - previous_end <= self._config.segment_merge_gap:
                merged_segments[-1] = (previous_start, end_row)
                continue
            merged_segments.append((start_row, end_row))

        crops: list[SegmentCrop] = []
        for start_row, end_row in merged_segments:
            top = max(0, start_row - self._config.segment_padding_y)
            bottom = min(image.height, end_row + self._config.segment_padding_y)
            if bottom - top < self._config.segment_min_height:
                continue
            bbox = (0, offset_top + top, image.width, offset_top + bottom)
            crops.append((bbox, image.crop((0, top, image.width, bottom))))

        if crops:
            return crops

        if image.height < self._config.segment_min_height:
            return []
        fallback_bbox = (0, offset_top, image.width, offset_top + image.height)
        return [(fallback_bbox, image)]

    def _estimate_background_color(self, rgb: np.ndarray) -> np.ndarray:
        height, width, _ = rgb.shape
        margin = max(1, min(self._config.segment_background_margin, width // 4, height // 4))
        samples = [
            rgb[:margin, :, :].reshape(-1, 3),
            rgb[-margin:, :, :].reshape(-1, 3),
            rgb[:, :margin, :].reshape(-1, 3),
            rgb[:, -margin:, :].reshape(-1, 3),
        ]
        combined = np.concatenate(samples, axis=0)
        return np.median(combined, axis=0)

    def _compute_segment_hash(self, image: Image.Image) -> int:
        resized = image.convert("L").resize((9, 8))
        pixels = np.asarray(resized, dtype=np.int16)
        diff = pixels[:, 1:] > pixels[:, :-1]
        hash_value = 0
        for bit in diff.flatten():
            hash_value = (hash_value << 1) | int(bit)
        return hash_value

    def _has_similar_segment_hash(self, current_hash: int) -> bool:
        return any(
            self._hamming_distance(current_hash, seen_hash) <= self._config.segment_hash_distance
            for seen_hash, _ in self._recent_segment_observations
        )

    def _is_duplicate_segment_text(
        self,
        current_hash: int,
        normalized_messages: tuple[str, ...],
    ) -> bool:
        for seen_hash, seen_messages in self._recent_segment_observations:
            if self._hamming_distance(current_hash, seen_hash) > self._config.segment_hash_distance:
                continue
            if normalized_messages == seen_messages:
                return True
        return False

    def _remember_segment_observation(
        self,
        current_hash: int,
        normalized_messages: tuple[str, ...],
    ) -> None:
        self._recent_segment_observations.append((current_hash, normalized_messages))
        while len(self._recent_segment_observations) > self._config.dedupe_cache_size:
            self._recent_segment_observations.popleft()

    def _hamming_distance(self, left: int, right: int) -> int:
        return (left ^ right).bit_count()

    def _normalize_message_text(self, message: ChatMessage) -> str:
        return " ".join(message.content.lower().split())
