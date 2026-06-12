#!/usr/bin/env python3
"""썸네일 합성 도구 (thumbnail-meta 스펙 → thumbnail.png).

1280x720. 배경 이미지(라이선스 확인 필수) 또는 단색 배경 + 큰 텍스트(3~5단어) +
채널 칩. 시니어 가독성: 고대비·굵은 글씨·모바일 축소판 판독 가능.

사용:
    python scripts/make_thumbnail.py <render_dir> --text "큰절하고 받던 전화"
        [--image <배경이미지>] [--accent "#c9a25a"] [--from-meta]

    --from-meta: <render_dir>/meta.json 의 thumbnail_spec{text, image}을 읽어 사용

요구: pip install pillow
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import find_korean_font

SIZE = (1280, 720)
BG = (29, 26, 22)
FG = (245, 238, 224)
OUTLINE = (12, 10, 8)


def hex_to_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def compose(out_path: Path, text: str, image: Path | None, accent: tuple[int, int, int]) -> None:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

    if image:
        base = ImageOps.fit(Image.open(image).convert("RGB"), SIZE)
        base = ImageEnhance.Brightness(base).enhance(0.62)  # 텍스트 대비 확보
    else:
        base = Image.new("RGB", SIZE, BG)

    d = ImageDraw.Draw(base)
    # 하단 그라데이션 (텍스트 받침)
    overlay = Image.new("L", (1, SIZE[1]), 0)
    for y in range(SIZE[1]):
        overlay.putpixel((0, y), min(200, max(0, int((y - SIZE[1] * 0.45) / (SIZE[1] * 0.55) * 200))))
    base.paste(Image.new("RGB", SIZE, OUTLINE), (0, 0), overlay.resize(SIZE))
    d = ImageDraw.Draw(base)

    font_path = find_korean_font()
    words = text.split()
    if len(words) > 5:
        print(f"경고: 썸네일 텍스트 {len(words)}단어 — 규칙은 3~5단어", file=sys.stderr)

    lines = textwrap.wrap(text, width=8)[:2] or [" "]
    font = ImageFont.truetype(font_path, 150 if len(lines) == 1 else 118)
    y = SIZE[1] - (len(lines) * (font.size + 18)) - 60
    d.rectangle([(64, y - 26), (64 + 130, y - 14)], fill=accent)  # 리딩라인
    for line in lines:
        d.text((64, y), line, font=font, fill=FG, stroke_width=10, stroke_fill=OUTLINE)
        y += font.size + 18

    chip_font = ImageFont.truetype(font_path, 38)
    d.text((64, 42), "역사산책", font=chip_font, fill=accent, stroke_width=4, stroke_fill=OUTLINE)

    base.save(out_path)


def main() -> int:
    p = argparse.ArgumentParser(description="썸네일 합성 (1280x720)")
    p.add_argument("render_dir", help="library/renders/<lang>/<slug>/")
    p.add_argument("--text", default=None, help="썸네일 문구 (3~5단어)")
    p.add_argument("--image", default=None, help="배경 이미지 (라이선스 확인 필수)")
    p.add_argument("--accent", default="#c9a25a")
    p.add_argument("--from-meta", action="store_true", help="meta.json thumbnail_spec 사용")
    p.add_argument("--out", default=None, help="출력 파일 (기본 <render_dir>/thumbnail.png)")
    args = p.parse_args()

    render_dir = Path(args.render_dir)
    text, image = args.text, args.image
    if args.from_meta:
        meta = json.loads((render_dir / "meta.json").read_text(encoding="utf-8"))
        spec = meta.get("thumbnail_spec", {})
        text = text or spec.get("text")
        image = image or spec.get("image")
    if not text:
        p.error("--text 또는 --from-meta(meta.json에 thumbnail_spec.text) 필요")

    out = Path(args.out) if args.out else render_dir / "thumbnail.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    compose(out, text, Path(image) if image else None, hex_to_rgb(args.accent))
    print(f"썸네일 저장: {out}")
    if image:
        print("주의: 배경 이미지 출처·라이선스를 assets.md에 기록하세요 (발행 게이트).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
