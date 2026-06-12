#!/usr/bin/env python3
"""yt-dlp 자막 추출 도구.

영상 URL에서 자막(수동 우선, 없으면 자동생성)을 내려받아 평문 텍스트로 정규화한다.
산출물은 '리서치 인풋' 전용이다 — 원문 문장을 대본에 복제하는 것은 저작권 가드레일 위반(CLAUDE.md).

사용:
    python scripts/yt_subtitles.py <video_url> [--lang ko] [--out sources/<slug>/raw/]

요구: pip install yt-dlp
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def fetch_metadata(url: str) -> dict:
    """yt-dlp로 영상 메타데이터(JSON)를 가져온다."""
    result = subprocess.run(
        ["yt-dlp", "--skip-download", "--dump-json", "--no-warnings", url],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def download_subtitle(url: str, lang: str, workdir: Path) -> Path | None:
    """자막 파일(vtt)을 내려받는다. 수동 자막 우선, 없으면 자동생성 자막."""
    for flag in ("--write-subs", "--write-auto-subs"):
        subprocess.run(
            [
                "yt-dlp", "--skip-download", flag,
                "--sub-langs", f"{lang},{lang}-*",
                "--sub-format", "vtt",
                "--no-warnings",
                "-o", str(workdir / "%(id)s.%(ext)s"),
                url,
            ],
            capture_output=True, text=True,
        )
        vtt_files = sorted(workdir.glob("*.vtt"))
        if vtt_files:
            return vtt_files[0]
    return None


def vtt_to_text(vtt_path: Path) -> str:
    """VTT 자막을 중복 제거된 평문으로 정규화한다."""
    lines: list[str] = []
    prev = ""
    for raw in vtt_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if (
            not line
            or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
            or "-->" in line
            or re.fullmatch(r"\d+", line)
        ):
            continue
        line = re.sub(r"<[^>]+>", "", line)  # 인라인 타이밍 태그 제거
        line = re.sub(r"\s+", " ", line).strip()
        if line and line != prev:
            lines.append(line)
            prev = line
    return "\n".join(lines)


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:max_len].rstrip("-") or "untitled"


def main() -> int:
    parser = argparse.ArgumentParser(description="yt-dlp 자막 추출 (리서치 인풋 전용)")
    parser.add_argument("url", help="영상 URL")
    parser.add_argument("--lang", default="ko", help="자막 언어 코드 (기본: ko)")
    parser.add_argument("--out", default=None, help="출력 디렉터리 (기본: sources/_inbox/<video_id>/)")
    args = parser.parse_args()

    try:
        meta = fetch_metadata(args.url)
    except subprocess.CalledProcessError as e:
        print(f"오류: 메타데이터 수집 실패 — {e.stderr.strip()[:500]}", file=sys.stderr)
        return 1

    video_id = meta.get("id", "unknown")
    out_dir = Path(args.out) if args.out else Path("sources/_inbox") / video_id
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        vtt = download_subtitle(args.url, args.lang, Path(tmp))
        if vtt is None:
            print(f"오류: '{args.lang}' 자막 없음 (수동/자동 모두)", file=sys.stderr)
            return 2
        text = vtt_to_text(vtt)

    title = meta.get("title", "untitled")
    base = f"{slugify(title)}-{video_id}"
    txt_path = out_dir / f"{base}.{args.lang}.txt"
    header = (
        f"# 자막 (리서치 인풋 전용 — 원문 복제 금지)\n"
        f"# 제목: {title}\n# 채널: {meta.get('channel', '?')}\n"
        f"# URL: {meta.get('webpage_url', args.url)}\n"
        f"# 조회수: {meta.get('view_count', '?')} | 업로드: {meta.get('upload_date', '?')}\n\n"
    )
    txt_path.write_text(header + text, encoding="utf-8")

    meta_path = out_dir / f"{base}.meta.json"
    keep = {k: meta.get(k) for k in (
        "id", "title", "channel", "channel_id", "webpage_url",
        "view_count", "like_count", "duration", "upload_date", "description",
    )}
    meta_path.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"저장: {txt_path}")
    print(f"메타: {meta_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
