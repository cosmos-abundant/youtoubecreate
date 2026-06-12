"""scripts/ 공용 헬퍼 — 한글 폰트 탐색, ffmpeg 실행."""
from __future__ import annotations

import subprocess
from pathlib import Path

KOREAN_FONT_CANDIDATES = [
    # Linux (fonts-nanum / noto-cjk)
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    # macOS
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/NanumGothicBold.ttf",
    # Windows
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/malgun.ttf",
]


def find_korean_font() -> str:
    for p in KOREAN_FONT_CANDIDATES:
        if Path(p).exists():
            return p
    # fontconfig 폴백
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{file}", ":lang=ko:weight=bold"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if out and Path(out).exists():
            return out
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    raise FileNotFoundError(
        "한글 폰트를 찾을 수 없습니다. fonts-nanum(리눅스) 설치 또는 "
        "환경에 맞는 경로를 _common.KOREAN_FONT_CANDIDATES에 추가하세요."
    )


def run_ffmpeg(args: list[str], desc: str = "") -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패{f' ({desc})' if desc else ''}:\n{result.stderr[-1500:]}")


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)
