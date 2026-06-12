#!/usr/bin/env python3
"""스톡 이미지·영상 검색/다운로드 (Pexels → Pixabay 폴백, MoneyPrinterTurbo 방식 차용).

씬의 검색어로 스톡 자산을 받아 렌더 폴더에 저장하고, 출처·라이선스를
stock-credits.json에 자동 기록한다 (assets.md 기입의 근거).

사용:
    python scripts/fetch_stock.py "old telephone vintage" --out library/renders/ko/<slug>/stock/
        [--type photo|video] [--orientation landscape] [--count 1]

API 키 (환경변수, 무료 발급):
    PEXELS_API_KEY   — https://www.pexels.com/api/
    PIXABAY_API_KEY  — https://pixabay.com/api/docs/

라이선스: Pexels License / Pixabay Content License — 무료 사용 가능, 출처 표기 권장.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _get(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _download(url: str, dst: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "youtube-factory/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        dst.write_bytes(r.read())


def search_pexels(query: str, media: str, orientation: str, count: int) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    q = urllib.parse.quote(query)
    if media == "video":
        data = _get(f"https://api.pexels.com/videos/search?query={q}&per_page={count}&orientation={orientation}",
                    {"Authorization": key})
        out = []
        for v in data.get("videos", []):
            files = sorted(v.get("video_files", []), key=lambda f: f.get("width") or 0, reverse=True)
            hd = next((f for f in files if (f.get("width") or 0) <= 1920), files[0] if files else None)
            if hd:
                out.append({"provider": "pexels", "id": v["id"], "url": hd["link"], "ext": "mp4",
                            "page": v.get("url"), "author": v.get("user", {}).get("name"),
                            "license": "Pexels License"})
        return out
    data = _get(f"https://api.pexels.com/v1/search?query={q}&per_page={count}&orientation={orientation}",
                {"Authorization": key})
    return [{"provider": "pexels", "id": p["id"], "url": p["src"]["large2x"], "ext": "jpg",
             "page": p.get("url"), "author": p.get("photographer"), "license": "Pexels License"}
            for p in data.get("photos", [])]


def search_pixabay(query: str, media: str, orientation: str, count: int) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    q = urllib.parse.quote(query)
    if media == "video":
        data = _get(f"https://pixabay.com/api/videos/?key={key}&q={q}&per_page={count}")
        return [{"provider": "pixabay", "id": v["id"],
                 "url": (v["videos"].get("large") or v["videos"]["medium"])["url"], "ext": "mp4",
                 "page": v.get("pageURL"), "author": v.get("user"),
                 "license": "Pixabay Content License"} for v in data.get("hits", [])]
    horiz = "horizontal" if orientation == "landscape" else "vertical"
    data = _get(f"https://pixabay.com/api/?key={key}&q={q}&per_page={count}&orientation={horiz}&image_type=photo")
    return [{"provider": "pixabay", "id": p["id"], "url": p["largeImageURL"], "ext": "jpg",
             "page": p.get("pageURL"), "author": p.get("user"),
             "license": "Pixabay Content License"} for p in data.get("hits", [])]


def fetch(query: str, out_dir: Path, media: str = "photo",
          orientation: str = "landscape", count: int = 1) -> list[dict]:
    """검색→다운로드→크레딧 기록. 받은 파일 메타 리스트를 반환."""
    results = search_pexels(query, media, orientation, count) or \
              search_pixabay(query, media, orientation, count)
    if not results:
        raise RuntimeError(
            "스톡 검색 결과 없음 — PEXELS_API_KEY/PIXABAY_API_KEY 설정 여부와 검색어(영어 권장)를 확인하세요.")
    out_dir.mkdir(parents=True, exist_ok=True)
    credits_path = out_dir / "stock-credits.json"
    credits = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.exists() else []
    saved = []
    for r in results[:count]:
        fname = f"{r['provider']}-{r['id']}.{r['ext']}"
        dst = out_dir / fname
        if not dst.exists():
            _download(r["url"], dst)
        entry = {**r, "file": fname, "query": query,
                 "fetched_at": datetime.now(timezone.utc).isoformat()}
        entry.pop("url", None)
        credits.append(entry)
        saved.append({**entry, "path": str(dst)})
        print(f"저장: {dst}  ({r['provider']}, {r['license']}, by {r.get('author')})")
    credits_path.write_text(json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8")
    return saved


def main() -> int:
    p = argparse.ArgumentParser(description="스톡 이미지·영상 다운로드 (Pexels→Pixabay)")
    p.add_argument("query", help="검색어 (영어 권장)")
    p.add_argument("--out", required=True, help="저장 디렉터리 (예: <render_dir>/stock/)")
    p.add_argument("--type", default="photo", choices=["photo", "video"], dest="media")
    p.add_argument("--orientation", default="landscape")
    p.add_argument("--count", type=int, default=1)
    args = p.parse_args()
    try:
        fetch(args.query, Path(args.out), args.media, args.orientation, args.count)
    except Exception as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
