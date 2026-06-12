#!/usr/bin/env python3
"""아웃라이어 점수 계산기.

아웃라이어 점수 = 조회수 ÷ 채널 중앙값(최근 20~50개).
임계값: 3배=분석가치 · 8배=심층연구 · 25배=돌파.

config/seed-channels.yaml 의 시드 채널을 순회하며 최근 영상 조회수를 수집하고,
최근 window_months 내 영상 중 임계값 이상을 후보로 출력한다.
판단(클러스터링·에버그린·소스 가용성)은 topic-scout 에이전트의 몫 — 이 스크립트는 계산만 한다.

사용:
    python scripts/outlier_score.py [--config config/seed-channels.yaml]
                                    [--channel <url>]      # 단일 채널 임시 분석
                                    [--out library/topics/_candidates.json]

요구: pip install yt-dlp pyyaml
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULTS = {
    "recent_videos": 50,
    "window_months": 6,
    "thresholds": {"analyze": 3, "deep_dive": 8, "breakout": 25},
}


def load_config(path: Path) -> dict:
    import yaml  # 지연 임포트: --channel 단독 사용 시 pyyaml 불필요

    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = {**DEFAULTS, **(cfg.get("defaults") or {})}
    defaults["thresholds"] = {**DEFAULTS["thresholds"], **(defaults.get("thresholds") or {})}
    channels = [c for c in (cfg.get("channels") or []) if c.get("enabled", True)]
    return {"defaults": defaults, "channels": channels}


def fetch_channel_videos(channel_url: str, limit: int) -> list[dict]:
    """채널의 최근 영상 메타데이터를 가져온다 (조회수·업로드일 포함)."""
    url = channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url += "/videos"
    result = subprocess.run(
        [
            "yt-dlp", "--flat-playlist", "--dump-json", "--no-warnings",
            "--extractor-args", "youtubetab:approximate_date",
            "--playlist-end", str(limit),
            url,
        ],
        capture_output=True, text=True,
    )
    videos = []
    for line in result.stdout.splitlines():
        try:
            v = json.loads(line)
        except json.JSONDecodeError:
            continue
        if v.get("view_count") is None:
            continue
        videos.append({
            "id": v.get("id"),
            "title": v.get("title"),
            "url": v.get("url") or f"https://www.youtube.com/watch?v={v.get('id')}",
            "view_count": v["view_count"],
            "upload_date": v.get("upload_date"),  # flat 모드에선 근사치/None 가능
            "duration": v.get("duration"),
        })
    return videos


def classify(score: float, thresholds: dict) -> str | None:
    if score >= thresholds["breakout"]:
        return "breakout"
    if score >= thresholds["deep_dive"]:
        return "deep_dive"
    if score >= thresholds["analyze"]:
        return "analyze"
    return None


def within_window(upload_date: str | None, months: int) -> bool:
    """업로드일이 윈도 내인지. 날짜 정보가 없으면 보수적으로 포함(에이전트가 확인)."""
    if not upload_date:
        return True
    try:
        dt = datetime.strptime(str(upload_date), "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return dt >= datetime.now(timezone.utc) - timedelta(days=months * 30)


def analyze_channel(channel: dict, defaults: dict) -> dict:
    videos = fetch_channel_videos(channel["url"], defaults["recent_videos"])
    if len(videos) < 5:
        return {"channel": channel.get("id", channel["url"]), "error": f"영상 수집 부족 ({len(videos)}개)"}

    median = statistics.median(v["view_count"] for v in videos)
    if median <= 0:
        return {"channel": channel.get("id", channel["url"]), "error": "중앙값 0"}

    outliers = []
    for v in videos:
        score = v["view_count"] / median
        tier = classify(score, defaults["thresholds"])
        if tier and within_window(v["upload_date"], defaults["window_months"]):
            outliers.append({**v, "outlier_score": round(score, 2), "tier": tier})
    outliers.sort(key=lambda x: x["outlier_score"], reverse=True)

    return {
        "channel": channel.get("id", channel["url"]),
        "channel_url": channel["url"],
        "niche": channel.get("niche"),
        "language": channel.get("language"),
        "sample_size": len(videos),
        "median_views": int(median),
        "outliers": outliers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="아웃라이어 점수 계산 (조회수 ÷ 채널 중앙값)")
    parser.add_argument("--config", default="config/seed-channels.yaml")
    parser.add_argument("--channel", default=None, help="단일 채널 URL (config 무시)")
    parser.add_argument("--out", default="library/topics/_candidates.json")
    args = parser.parse_args()

    if args.channel:
        defaults = DEFAULTS
        channels = [{"id": args.channel, "url": args.channel}]
    else:
        cfg_path = Path(args.config)
        if not cfg_path.exists():
            print(f"오류: 설정 파일 없음 — {cfg_path}", file=sys.stderr)
            return 1
        cfg = load_config(cfg_path)
        defaults, channels = cfg["defaults"], cfg["channels"]
        if not channels:
            print("오류: enabled 채널이 없음. config/seed-channels.yaml에 시드 채널을 추가하세요.", file=sys.stderr)
            return 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "defaults": defaults,
        "results": [],
    }
    for ch in channels:
        print(f"분석 중: {ch.get('id', ch['url'])} …", file=sys.stderr)
        report["results"].append(analyze_channel(ch, defaults))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(len(r.get("outliers", [])) for r in report["results"])
    print(f"\n채널 {len(channels)}개 분석, 아웃라이어 {total}건 → {out_path}")
    for r in report["results"]:
        for o in r.get("outliers", [])[:5]:
            print(f"  [{o['tier']:>9}] {o['outlier_score']:>6.1f}x  {r['channel']}  {o['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
