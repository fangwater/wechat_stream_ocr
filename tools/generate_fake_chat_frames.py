from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


DEFAULT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate synthetic chat frames for OCR testing")
    parser.add_argument(
        "--output-dir",
        default="samples/generated",
        help="Directory where the generated PNG files will be written",
    )
    parser.add_argument(
        "--font-path",
        default=DEFAULT_FONT,
        help="Font used to draw the synthetic text",
    )
    return parser


def draw_frame(messages: list[str], font_path: str) -> Image.Image:
    width = 1440
    height = 900
    image = Image.new("RGB", (width, height), "#f5f5f5")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 42)
    bubble_font = ImageFont.truetype(font_path, 36)

    draw.rectangle((320, 80, 1320, 820), fill="white")
    draw.rectangle((320, 80, 1320, 140), fill="#ededed")
    draw.text((360, 94), "Synthetic Chat Window", fill="#202020", font=font)

    top = 180
    for index, text in enumerate(messages):
        bubble_top = top + index * 120
        draw.rounded_rectangle((420, bubble_top, 1220, bubble_top + 84), radius=18, fill="#dcf8c6")
        draw.text((460, bubble_top + 22), text, fill="#101010", font=bubble_font)

    return image


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    before_frame = draw_frame(
        ["Alice 2026-03-30 13:40:00 status ready"],
        args.font_path,
    )
    after_frame = draw_frame(
        [
            "Alice 2026-03-30 13:40:00 status ready",
            "Alice 2026-03-30 13:45:00 task done",
        ],
        args.font_path,
    )

    before_path = output_dir / "frame_before.png"
    after_path = output_dir / "frame_after.png"
    before_frame.save(before_path)
    after_frame.save(after_path)

    print(before_path)
    print(after_path)


if __name__ == "__main__":
    main()
