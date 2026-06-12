#!/usr/bin/env python3
"""영상 제작 엔진 (video-producer의 결정론적 하류).

대본(draft-v*.md)의 <!-- scene: --> 주석을 기준으로 씬 분할 → 씬별 TTS →
비주얼(이미지 또는 자동 텍스트 카드) → ffmpeg 조립 → final.mp4.
결과물은 전부 --out 디렉터리(기본 library/renders/ko/<slug>/)에 저장된다.

사용:
    python scripts/produce_video.py library/scripts/<slug>/draft-v2.md
        [--out library/renders/ko/<slug>]
        [--tts edge|none] [--voice ko-KR-InJoonNeural] [--rate -7%]
        [--resolution 1920x1080] [--bgm <파일>] [--scenes-only]

TTS 엔진:
    edge  : edge-tts (무료, 한국어 신경망 음성. pip install edge-tts, 인터넷 필요) — 기본값
    none  : 무음 (분당 300자 기준 길이 추정) — 파이프라인 검증·타이밍 시안용
    (supertone / elevenlabs는 API 키 확보 후 _synthesize()에 추가)

워크플로:
    1. 1차 실행(--scenes-only) → scenes.json 생성
    2. video-producer 에이전트/사람이 scenes.json의 image·card_text를 다듬음 (선택)
    3. 재실행 → 수동 수정을 보존한 채 TTS·렌더 (image 파일은 라이선스 확인 후 assets.md에 기록)

요구: ffmpeg(시스템), pip install pillow edge-tts
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import find_korean_font, probe_duration, run_ffmpeg

CHARS_PER_MIN = 300          # 시니어 친화 낭독 속도 (무음 모드 길이 추정)
SCENE_GAP_SEC = 0.6          # 씬 사이 여백 (호흡)
DEFAULT_VOICE = "ko-KR-InJoonNeural"   # 차분한 남성 톤. 대안: ko-KR-SunHiNeural(여성)
DEFAULT_RATE = "-7%"         # 시니어 친화: 기본보다 천천히

# 텍스트 카드 팔레트 (시니어 친화: 고대비, 채널 톤: 고서 질감 느낌의 차분한 색)
CARD_BG = (29, 26, 22)       # 짙은 먹색
CARD_FG = (242, 232, 213)    # 미색
CARD_ACCENT = (201, 162, 90) # 황동색 (포인트 라인)


# ---------------------------------------------------------------- 씬 분할

def parse_scenes(draft_path: Path) -> list[dict]:
    """<!-- scene: ... --> 주석으로 대본을 씬 단위로 나눈다."""
    text = draft_path.read_text(encoding="utf-8")
    # 제목(# ...)과 일반 주석은 낭독 대상에서 제외
    text = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)
    parts = re.split(r"<!--\s*scene:\s*(.*?)\s*-->", text)
    # parts = [씬0 앞 텍스트, hint1, 본문1, hint2, 본문2, ...]
    scenes: list[dict] = []
    preamble = parts[0].strip()
    if preamble:  # scene 주석 이전 텍스트가 있으면 첫 씬으로
        scenes.append({"visual_hint": "(지정 없음)", "text": preamble})
    for i in range(1, len(parts) - 1, 2):
        body = re.sub(r"<!--.*?-->", "", parts[i + 1], flags=re.DOTALL).strip()
        if body:
            scenes.append({"visual_hint": parts[i], "text": re.sub(r"\n{2,}", "\n", body)})
    if not scenes:
        raise ValueError(f"씬을 찾지 못했습니다 — {draft_path}에 <!-- scene: --> 주석이 있는지 확인")
    for n, s in enumerate(scenes, 1):
        s["id"] = n
        s["card_text"] = _default_card_text(s["visual_hint"])
        s["image"] = None  # 라이선스 확인된 이미지 경로를 넣으면 카드 대신 사용
    return scenes


def _default_card_text(hint: str) -> str:
    """비주얼 힌트에서 카드에 띄울 짧은 문구를 만든다 (조사·지시문 제거는 사람/에이전트 몫)."""
    return hint.split(",")[0].strip()[:24] or "역사산책"


def load_or_merge_scenes(draft_path: Path, scenes_path: Path) -> list[dict]:
    """기존 scenes.json의 수동 수정(image, card_text)을 보존하며 대본과 동기화."""
    fresh = parse_scenes(draft_path)
    if scenes_path.exists():
        old = {s["id"]: s for s in json.loads(scenes_path.read_text(encoding="utf-8"))["scenes"]}
        for s in fresh:
            o = old.get(s["id"])
            if o and o.get("text") == s["text"]:  # 본문이 같을 때만 수동 필드 승계
                s["image"] = o.get("image")
                s["card_text"] = o.get("card_text", s["card_text"])
    return fresh


# ---------------------------------------------------------------- TTS

def synthesize_all(scenes: list[dict], out_dir: Path, engine: str, voice: str, rate: str) -> None:
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for s in scenes:
        path = audio_dir / f"scene-{s['id']:02d}.mp3"
        if engine == "edge":
            _edge_tts(s["text"], path, voice, rate)
            s["duration"] = round(probe_duration(path) + SCENE_GAP_SEC, 2)
        elif engine == "none":
            est = max(3.0, len(re.sub(r"\s", "", s["text"])) / CHARS_PER_MIN * 60)
            run_ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                        "-t", f"{est:.2f}", "-q:a", "9", str(path)], "무음 생성")
            s["duration"] = round(est + SCENE_GAP_SEC, 2)
        else:
            raise ValueError(f"미지원 TTS 엔진: {engine} (supertone/elevenlabs는 API 키 확보 후 추가)")
        s["audio"] = str(path.relative_to(out_dir))
        print(f"  씬 {s['id']:02d} 오디오 {s['duration']:>6.1f}s ({engine})", file=sys.stderr)


def _edge_tts(text: str, path: Path, voice: str, rate: str) -> None:
    import edge_tts

    async def _run():
        await edge_tts.Communicate(text, voice, rate=rate).save(str(path))

    asyncio.run(_run())
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("edge-tts 결과가 비어 있음 (네트워크 차단 환경이면 --tts none 사용)")


# ---------------------------------------------------------------- 비주얼

def make_card(scene: dict, size: tuple[int, int], path: Path, font_path: str) -> None:
    """이미지 미지정 씬용 텍스트 카드 (큰 글씨·고대비)."""
    from PIL import Image, ImageDraw, ImageFont

    w, h = size
    img = Image.new("RGB", size, CARD_BG)
    d = ImageDraw.Draw(img)
    d.rectangle([(int(w * 0.08), int(h * 0.46)), (int(w * 0.13), int(h * 0.465))], fill=CARD_ACCENT)

    font_big = ImageFont.truetype(font_path, int(h * 0.075))
    font_small = ImageFont.truetype(font_path, int(h * 0.03))
    lines = textwrap.wrap(scene["card_text"], width=12) or [" "]
    y = int(h * 0.50)
    for line in lines[:3]:
        d.text((int(w * 0.08), y), line, font=font_big, fill=CARD_FG)
        y += int(h * 0.10)
    d.text((int(w * 0.08), int(h * 0.88)), f"역사산책 · {scene['id']:02d}",
           font=font_small, fill=CARD_ACCENT)
    img.save(path)


def prepare_visual(scene: dict, size: tuple[int, int], out_dir: Path, font_path: str) -> Path:
    frames = out_dir / "frames"
    frames.mkdir(exist_ok=True)
    dst = frames / f"scene-{scene['id']:02d}.png"
    if scene.get("image"):
        src = Path(scene["image"])
        if not src.exists():
            raise FileNotFoundError(f"씬 {scene['id']} 이미지 없음: {src}")
        _fit_image(src, dst, size)
    else:
        make_card(scene, size, dst, font_path)
    return dst


def _fit_image(src: Path, dst: Path, size: tuple[int, int]) -> None:
    """비율 유지 + 여백 채움(레터박스)으로 해상도에 맞춘다."""
    from PIL import Image, ImageOps

    img = Image.open(src).convert("RGB")
    canvas = Image.new("RGB", size, CARD_BG)
    fitted = ImageOps.contain(img, size)
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    canvas.save(dst)


# ---------------------------------------------------------------- 조립

def render(scenes: list[dict], out_dir: Path, size: tuple[int, int], bgm: Path | None) -> Path:
    seg_dir = out_dir / "segments"
    seg_dir.mkdir(exist_ok=True)
    font_path = find_korean_font()
    seg_paths = []
    for s in scenes:
        frame = prepare_visual(s, size, out_dir, font_path)
        seg = seg_dir / f"scene-{s['id']:02d}.mp4"
        run_ffmpeg([
            "-loop", "1", "-framerate", "24", "-i", str(frame),
            "-i", str(out_dir / s["audio"]),
            "-t", f"{s['duration']:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-af", f"apad=pad_dur={SCENE_GAP_SEC}",
            str(seg),
        ], f"씬 {s['id']} 렌더")
        seg_paths.append(seg)
        print(f"  씬 {s['id']:02d} 렌더 완료", file=sys.stderr)

    concat_list = seg_dir / "concat.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in seg_paths), encoding="utf-8")
    final = out_dir / "final.mp4"
    if bgm:
        run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex",
            "[1:a]volume=-18dB[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
            str(final),
        ], "BGM 합성")
    else:
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(final)],
                   "최종 결합")
    return final


def write_assets_ledger(out_dir: Path, scenes: list[dict], bgm: Path | None) -> None:
    """이미지·BGM 라이선스 대장 스켈레톤 (저작권 가드레일 — 발행 전 100% 기입 필수)."""
    path = out_dir / "assets.md"
    if path.exists():
        return
    rows = ["# 에셋 라이선스 대장 (발행 전 전 항목 기입 필수)", "",
            "| 에셋 | 씬 | 출처 | 라이선스 | 확인일 |", "|---|---|---|---|---|"]
    for s in scenes:
        asset = s.get("image") or f"(자동 텍스트 카드 — frames/scene-{s['id']:02d}.png, 자체 생성)"
        license_ = "자체 생성" if not s.get("image") else "**미확인 — 기입 필요**"
        rows.append(f"| {asset} | {s['id']} | | {license_} | |")
    rows.append(f"| BGM: {bgm or '(없음)'} | 전체 | | {'**미확인 — 기입 필요**' if bgm else '-'} | |")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description="대본 → 영상 제작 (씬분할·TTS·렌더)")
    p.add_argument("draft", help="library/scripts/<slug>/draft-v*.md")
    p.add_argument("--out", default=None, help="출력 디렉터리 (기본 library/renders/ko/<slug>)")
    p.add_argument("--tts", default="edge", choices=["edge", "none"])
    p.add_argument("--voice", default=DEFAULT_VOICE)
    p.add_argument("--rate", default=DEFAULT_RATE)
    p.add_argument("--resolution", default="1920x1080")
    p.add_argument("--bgm", default=None, help="BGM 파일 (라이선스 확인 필수, -18dB 믹스)")
    p.add_argument("--scenes-only", action="store_true", help="scenes.json만 생성하고 종료")
    args = p.parse_args()

    draft = Path(args.draft)
    slug = draft.parent.name
    out_dir = Path(args.out) if args.out else Path("library/renders/ko") / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    size = tuple(int(x) for x in args.resolution.split("x"))
    scenes_path = out_dir / "scenes.json"

    scenes = load_or_merge_scenes(draft, scenes_path)
    if args.scenes_only:
        _save_scenes(scenes_path, slug, draft, args, scenes)
        print(f"scenes.json 생성: {scenes_path} — image/card_text 수정 후 재실행하세요.")
        return 0

    print(f"씬 {len(scenes)}개 — TTS({args.tts}) 합성 중…", file=sys.stderr)
    synthesize_all(scenes, out_dir, args.tts, args.voice, args.rate)
    _save_scenes(scenes_path, slug, draft, args, scenes)

    print("렌더링 중…", file=sys.stderr)
    final = render(scenes, out_dir, size, Path(args.bgm) if args.bgm else None)
    write_assets_ledger(out_dir, scenes, Path(args.bgm) if args.bgm else None)

    total = sum(s["duration"] for s in scenes)
    print(f"\n완성: {final}  (씬 {len(scenes)}개, {total/60:.1f}분)")
    print(f"체크: scenes.json·assets.md 확인 → 썸네일(make_thumbnail.py) → meta.json(thumbnail-meta)")
    return 0


def _save_scenes(path: Path, slug: str, draft: Path, args, scenes: list[dict]) -> None:
    path.write_text(json.dumps({
        "slug": slug,
        "source_draft": str(draft),
        "tts": {"engine": args.tts, "voice": args.voice, "rate": args.rate},
        "scenes": scenes,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
