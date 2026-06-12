#!/usr/bin/env python3
"""영상 제작 엔진 (video-producer의 결정론적 하류).

대본의 <!-- scene: --> 주석 기준 씬 분할 → 씬별 TTS → 비주얼 → 켄번즈 모션 →
번인 자막 → ffmpeg 조립 → final.mp4. 결과물은 --out 디렉터리에 저장.

비주얼 타입 (씬별 혼합 — config/video-modes.yaml 참조):
    card      자체 생성 텍스트 카드 (기본 폴백, 비용 0)
    stock     스톡 사진·영상 — visual.query로 자동 다운로드(fetch_stock.py) 또는 file 지정
    ai-image  AI 생성 이미지 (하이퍼프레임식) — 에이전트가 MCP/API로 생성해 file에 배치
    ai-video  AI 생성 클립 (Kling/Veo 등) — 에이전트가 MCP로 생성해 file에 배치
    file      라이선스 확인된 임의 파일 (사진·영상)

공통 기본기: 정지 이미지에 켄번즈(zoom/pan), 문장 단위 번인 자막(시니어 가독),
씬 페이드, 씬 간 0.6초 호흡, BGM -18dB 믹스.

사용:
    python scripts/produce_video.py library/scripts/<slug>/draft-v2.md
        [--out DIR] [--tts edge|none] [--voice ...] [--rate -7%]
        [--resolution 1920x1080] [--bgm 파일] [--no-subtitles] [--scenes-only]

요구: ffmpeg(libass 포함), pip install pillow edge-tts
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

CHARS_PER_MIN = 300
SCENE_GAP_SEC = 0.6
FPS = 24
DEFAULT_VOICE = "ko-KR-InJoonNeural"
DEFAULT_RATE = "-7%"

CARD_BG = (29, 26, 22)
CARD_FG = (242, 232, 213)
CARD_ACCENT = (201, 162, 90)

MOTIONS = ("zoom-in", "zoom-out", "pan-left", "pan-right", "none")
VISUAL_TYPES = ("card", "stock", "ai-image", "ai-video", "file")
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}


# ---------------------------------------------------------------- 씬 분할

def parse_scenes(draft_path: Path) -> list[dict]:
    """<!-- scene: ... --> 주석으로 대본을 씬 단위로 나눈다."""
    text = draft_path.read_text(encoding="utf-8")
    text = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)
    parts = re.split(r"<!--\s*scene:\s*(.*?)\s*-->", text)
    scenes: list[dict] = []
    preamble = parts[0].strip()
    if preamble:
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
        # 기본 모션: 줌인/줌아웃 교차 (정지화면이 살아 있게 — 켄번즈)
        s["visual"] = {"type": "card", "file": None, "query": None, "prompt": None,
                       "motion": MOTIONS[(n - 1) % 2]}
    return scenes


def _default_card_text(hint: str) -> str:
    return hint.split(",")[0].strip()[:24] or "역사산책"


def load_or_merge_scenes(draft_path: Path, scenes_path: Path) -> list[dict]:
    """기존 scenes.json의 수동 수정(visual, card_text)을 보존하며 대본과 동기화."""
    fresh = parse_scenes(draft_path)
    if scenes_path.exists():
        old = {s["id"]: s for s in json.loads(scenes_path.read_text(encoding="utf-8"))["scenes"]}
        for s in fresh:
            o = old.get(s["id"])
            if o and o.get("text") == s["text"]:
                s["card_text"] = o.get("card_text", s["card_text"])
                if o.get("visual"):
                    s["visual"] = {**s["visual"], **o["visual"]}
                elif o.get("image"):  # 구버전 스키마 호환
                    s["visual"]["type"] = "file"
                    s["visual"]["file"] = o["image"]
    return fresh


def split_sentences(text: str) -> list[str]:
    """자막 큐 단위 문장 분리."""
    flat = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?…])\s+", flat)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------- TTS (+자막 타이밍)

def synthesize_all(scenes: list[dict], out_dir: Path, engine: str, voice: str, rate: str) -> None:
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for s in scenes:
        path = audio_dir / f"scene-{s['id']:02d}.mp3"
        if engine == "edge":
            words = _edge_tts(s["text"], path, voice, rate)
            dur = probe_duration(path)
            s["cues"] = _cues_from_words(split_sentences(s["text"]), words, dur)
        elif engine == "none":
            dur = max(3.0, len(re.sub(r"\s", "", s["text"])) / CHARS_PER_MIN * 60)
            run_ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                        "-t", f"{dur:.2f}", "-q:a", "9", str(path)], "무음 생성")
            s["cues"] = _cues_proportional(split_sentences(s["text"]), dur)
        else:
            raise ValueError(f"미지원 TTS 엔진: {engine}")
        s["audio"] = str(path.relative_to(out_dir))
        s["duration"] = round(dur + SCENE_GAP_SEC, 2)
        print(f"  씬 {s['id']:02d} 오디오 {s['duration']:>6.1f}s ({engine})", file=sys.stderr)


def _edge_tts(text: str, path: Path, voice: str, rate: str) -> list[dict]:
    """오디오 저장 + 워드 바운더리(자막 타이밍) 수집."""
    import edge_tts

    words: list[dict] = []

    async def _run():
        comm = edge_tts.Communicate(text, voice, rate=rate)
        with open(path, "wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    words.append({"t": chunk["offset"] / 1e7, "d": chunk["duration"] / 1e7,
                                  "w": chunk["text"]})

    asyncio.run(_run())
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("edge-tts 결과가 비어 있음 (네트워크 차단 환경이면 --tts none 사용)")
    return words


def _cues_from_words(sentences: list[str], words: list[dict], total: float) -> list[dict]:
    """워드 바운더리를 문장에 귀속시켜 자막 큐 생성 (글자수 누적 매칭)."""
    if not words:
        return _cues_proportional(sentences, total)
    cues, wi = [], 0
    for sent in sentences:
        target = len(re.sub(r"[\s\W]", "", sent, flags=re.UNICODE))
        start = words[wi]["t"] if wi < len(words) else total
        acc = 0
        while wi < len(words) and acc < max(1, target):
            acc += len(re.sub(r"[\s\W]", "", words[wi]["w"], flags=re.UNICODE))
            wi += 1
        end = (words[wi - 1]["t"] + words[wi - 1]["d"]) if wi > 0 else total
        cues.append({"start": round(start, 3), "end": round(min(end + 0.15, total), 3), "text": sent})
    return cues


def _cues_proportional(sentences: list[str], total: float) -> list[dict]:
    """무음 모드: 글자수 비례 타이밍 분배."""
    weights = [max(1, len(re.sub(r"\s", "", s))) for s in sentences]
    wsum, t, cues = sum(weights), 0.0, []
    for sent, w in zip(sentences, weights):
        d = total * w / wsum
        cues.append({"start": round(t, 3), "end": round(t + d, 3), "text": sent})
        t += d
    return cues


def write_srt(cues: list[dict], path: Path) -> None:
    def ts(sec: float) -> str:
        ms = int(round(sec * 1000))
        return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"

    lines = []
    for i, c in enumerate(cues, 1):
        lines += [str(i), f"{ts(c['start'])} --> {ts(c['end'])}", c["text"], ""]
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- 비주얼

def make_card(scene: dict, size: tuple[int, int], path: Path, font_path: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    w, h = size
    img = Image.new("RGB", size, CARD_BG)
    d = ImageDraw.Draw(img)
    d.rectangle([(int(w * 0.08), int(h * 0.42)), (int(w * 0.13), int(h * 0.425))], fill=CARD_ACCENT)
    font_big = ImageFont.truetype(font_path, int(h * 0.075))
    font_small = ImageFont.truetype(font_path, int(h * 0.03))
    y = int(h * 0.46)
    for line in (textwrap.wrap(scene["card_text"], width=12) or [" "])[:3]:
        d.text((int(w * 0.08), y), line, font=font_big, fill=CARD_FG)
        y += int(h * 0.10)
    d.text((int(w * 0.08), int(h * 0.06)), "역사산책", font=font_small, fill=CARD_ACCENT)
    img.save(path)


def resolve_visual(scene: dict, size: tuple[int, int], out_dir: Path, font_path: str) -> tuple[str, Path]:
    """씬의 비주얼 소스를 확정한다. 반환: ("image"|"video", 파일경로)."""
    v = scene.get("visual") or {}
    vtype = v.get("type", "card")
    if vtype not in VISUAL_TYPES:
        raise ValueError(f"씬 {scene['id']}: 미지원 visual.type '{vtype}' (가능: {VISUAL_TYPES})")

    if vtype != "card" and v.get("file"):
        src = (out_dir / v["file"]) if not Path(v["file"]).is_absolute() else Path(v["file"])
        if not src.exists():
            src = Path(v["file"])  # 저장소 상대 경로 재시도
        if not src.exists():
            raise FileNotFoundError(
                f"씬 {scene['id']} ({vtype}): 파일 없음 — {v['file']}\n"
                f"  ai-image/ai-video는 에이전트가 MCP/API로 생성해 배치해야 합니다 "
                f"(docs/video-production.md 참조)")
        return ("video" if src.suffix.lower() in VIDEO_EXTS else "image", src)

    if vtype == "stock":
        if not v.get("query"):
            raise ValueError(f"씬 {scene['id']}: stock 타입은 visual.query 또는 visual.file 필요")
        from fetch_stock import fetch
        media = "video" if v.get("media") == "video" else "photo"
        saved = fetch(v["query"], out_dir / "stock", media=media)
        v["file"] = str(Path(saved[0]["path"]).relative_to(out_dir))
        return ("video" if media == "video" else "image", Path(saved[0]["path"]))

    if vtype in ("ai-image", "ai-video"):
        raise FileNotFoundError(
            f"씬 {scene['id']} ({vtype}): visual.file 미지정 — 에이전트가 생성 파일을 "
            f"genai/scene-{scene['id']:02d}.* 로 배치하고 file에 기록해야 합니다")

    # card
    frames = out_dir / "frames"
    frames.mkdir(exist_ok=True)
    dst = frames / f"scene-{scene['id']:02d}.png"
    make_card(scene, size, dst, font_path)
    return ("image", dst)


# ---------------------------------------------------------------- 모션·필터

def kenburns_expr(motion: str, frames: int) -> str:
    """켄번즈 zoompan 필터 (정지 이미지 → 살아 있는 화면)."""
    z_max = 1.10
    center = "x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'"
    if motion == "zoom-in":
        return f"zoompan=z='1+{z_max - 1:.2f}*on/{frames}':{center}"
    if motion == "zoom-out":
        return f"zoompan=z='{z_max:.2f}-{z_max - 1:.2f}*on/{frames}':{center}"
    if motion == "pan-left":
        return f"zoompan=z='1.08':x='(iw-iw/zoom)*(1-on/{frames})':y='(ih-ih/zoom)/2'"
    if motion == "pan-right":
        return f"zoompan=z='1.08':x='(iw-iw/zoom)*on/{frames}':y='(ih-ih/zoom)/2'"
    return f"zoompan=z='1.001':{center}"  # none: 프레임 복제만


def build_video_filter(kind: str, scene: dict, size: tuple[int, int],
                       srt: Path | None, dur: float) -> str:
    w, h = size
    steps = []
    if kind == "image":
        frames = max(2, int(round(dur * FPS)))
        motion = (scene.get("visual") or {}).get("motion", "none")
        steps.append(f"scale=-2:{h * 2}")  # 업스케일 후 줌 (지터 완화)
        steps.append(kenburns_expr(motion if motion in MOTIONS else "none", frames)
                     + f":d={frames}:s={w}x{h}:fps={FPS}")
    else:  # video
        steps.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease")
        steps.append(f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x1d1a16")
        steps.append(f"fps={FPS}")
    if srt:
        srt_esc = str(srt.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        style = ("FontName=NanumGothic,Bold=1,FontSize=15,PrimaryColour=&H00E0EEF5,"
                 "OutlineColour=&H00100E0C,Outline=2,BorderStyle=1,MarginV=36")
        steps.append(f"subtitles='{srt_esc}':force_style='{style}'")
    fade_out = max(0.0, dur - 0.4)
    steps.append(f"fade=t=in:st=0:d=0.35,fade=t=out:st={fade_out:.2f}:d=0.35")
    return ",".join(steps)


# ---------------------------------------------------------------- 조립

def render(scenes: list[dict], out_dir: Path, size: tuple[int, int],
           bgm: Path | None, subtitles: bool) -> Path:
    seg_dir = out_dir / "segments"
    subs_dir = out_dir / "subs"
    seg_dir.mkdir(exist_ok=True)
    subs_dir.mkdir(exist_ok=True)
    font_path = find_korean_font()
    seg_paths = []
    for s in scenes:
        kind, src = resolve_visual(s, size, out_dir, font_path)
        srt = None
        if subtitles and s.get("cues"):
            srt = subs_dir / f"scene-{s['id']:02d}.srt"
            write_srt(s["cues"], srt)
        vf = build_video_filter(kind, s, size, srt, s["duration"])
        seg = seg_dir / f"scene-{s['id']:02d}.mp4"
        in_args = (["-loop", "1", "-framerate", str(FPS), "-i", str(src)] if kind == "image"
                   else ["-stream_loop", "-1", "-i", str(src)])
        run_ffmpeg([
            *in_args, "-i", str(out_dir / s["audio"]),
            "-t", f"{s['duration']:.2f}", "-vf", vf,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-af", f"apad=pad_dur={SCENE_GAP_SEC}",
            str(seg),
        ], f"씬 {s['id']} 렌더")
        seg_paths.append(seg)
        print(f"  씬 {s['id']:02d} 렌더 완료 ({kind}, {(s.get('visual') or {}).get('type')})",
              file=sys.stderr)

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
    path = out_dir / "assets.md"
    if path.exists():
        return
    rows = ["# 에셋 라이선스 대장 (발행 전 전 항목 기입 필수)", "",
            "stock 타입은 stock/stock-credits.json에 출처가 자동 기록됨 — 여기 옮겨 적는다.",
            "ai-image/ai-video는 생성 모델·프롬프트를 기록한다.", "",
            "| 씬 | 타입 | 파일/프롬프트 | 출처 | 라이선스 | 확인일 |", "|---|---|---|---|---|---|"]
    for s in scenes:
        v = s.get("visual") or {}
        vtype = v.get("type", "card")
        ref = v.get("file") or v.get("prompt") or v.get("query") or "(자동 카드)"
        license_ = "자체 생성" if vtype == "card" else "**기입 필요**"
        rows.append(f"| {s['id']} | {vtype} | {ref} | | {license_} | |")
    rows.append(f"| 전체 | BGM | {bgm or '(없음)'} | | {'**기입 필요**' if bgm else '-'} | |")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description="대본 → 영상 제작 (씬분할·TTS·모션·자막·렌더)")
    p.add_argument("draft")
    p.add_argument("--out", default=None)
    p.add_argument("--tts", default="edge", choices=["edge", "none"])
    p.add_argument("--voice", default=DEFAULT_VOICE)
    p.add_argument("--rate", default=DEFAULT_RATE)
    p.add_argument("--resolution", default="1920x1080")
    p.add_argument("--bgm", default=None)
    p.add_argument("--no-subtitles", action="store_true")
    p.add_argument("--scenes-only", action="store_true")
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
        print(f"scenes.json 생성: {scenes_path}")
        print("다음: 씬별 visual(type/query/file/motion)·card_text 지정 후 재실행 "
              "(타입 가이드: config/video-modes.yaml)")
        return 0

    print(f"씬 {len(scenes)}개 — TTS({args.tts}) 합성 중…", file=sys.stderr)
    synthesize_all(scenes, out_dir, args.tts, args.voice, args.rate)
    _save_scenes(scenes_path, slug, draft, args, scenes)

    print("렌더링 중…", file=sys.stderr)
    final = render(scenes, out_dir, size, Path(args.bgm) if args.bgm else None,
                   subtitles=not args.no_subtitles)
    write_assets_ledger(out_dir, scenes, Path(args.bgm) if args.bgm else None)
    _save_scenes(scenes_path, slug, draft, args, scenes)  # stock 자동 다운로드 등 갱신 반영

    total = sum(s["duration"] for s in scenes)
    print(f"\n완성: {final}  (씬 {len(scenes)}개, {total/60:.1f}분)")
    print("체크: scenes.json·assets.md → 썸네일(make_thumbnail.py) → meta.json(thumbnail-meta)")
    return 0


def _save_scenes(path: Path, slug: str, draft: Path, args, scenes: list[dict]) -> None:
    slim = []
    for s in scenes:
        c = dict(s)
        c.pop("cues", None)  # 자막 타이밍은 subs/*.srt로 충분
        slim.append(c)
    path.write_text(json.dumps({
        "slug": slug, "source_draft": str(draft),
        "tts": {"engine": args.tts, "voice": args.voice, "rate": args.rate},
        "scenes": slim,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
