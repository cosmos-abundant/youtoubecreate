#!/usr/bin/env python3
"""YouTube Analytics API 성과 데이터 회수 도구 (mode-improver의 입력 생성).

library/published.json 의 발행 영상별로 조회수·시청지속 지표를 수집해
library/analytics/<date>.json 으로 저장한다. 판단·모드 업데이트는 mode-improver의 몫.

한계: 썸네일 노출수·CTR은 Analytics API가 제공하지 않는다(YouTube Studio에서만 확인 가능).
      해당 필드는 null로 두고, mode-improver가 수동 입력을 요청한다.

사용:
    python scripts/fetch_analytics.py [--days 7] [--lang ko]

인증: client_secrets.json + 최초 1회 브라우저 인증 → .credentials/token-analytics.json
요구: pip install google-api-python-client google-auth-oauthlib
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]
PUBLISHED_PATH = Path("library/published.json")
OUT_DIR = Path("library/analytics")
METRICS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,subscribersGained"


def get_service():
    import os

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    secrets = Path(os.environ.get("YT_CLIENT_SECRETS", "client_secrets.json"))
    token_path = Path(".credentials/token-analytics.json")
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secrets.exists():
                raise FileNotFoundError(f"OAuth 클라이언트 파일 없음: {secrets}")
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("youtubeAnalytics", "v2", credentials=creds)


def query_video(service, video_id: str, start: str, end: str) -> dict | None:
    resp = service.reports().query(
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        metrics=METRICS,
        filters=f"video=={video_id}",
    ).execute()
    rows = resp.get("rows") or []
    if not rows:
        return None
    headers = [h["name"] for h in resp["columnHeaders"]]
    return dict(zip(headers, rows[0]))


def main() -> int:
    parser = argparse.ArgumentParser(description="발행 영상 성과 데이터 회수")
    parser.add_argument("--days", type=int, default=7, help="발행일 기준 측정 기간 (기본 7)")
    parser.add_argument("--lang", default=None, help="특정 언어 채널만 (ko/en)")
    args = parser.parse_args()

    if not PUBLISHED_PATH.exists():
        print("오류: library/published.json 없음 — 발행 영상이 없습니다.", file=sys.stderr)
        return 1
    published = json.loads(PUBLISHED_PATH.read_text(encoding="utf-8"))
    if args.lang:
        published = [r for r in published if r.get("language") == args.lang]
    if not published:
        print("측정 대상 영상 없음.")
        return 0

    service = get_service()
    today = datetime.now(timezone.utc).date()
    results = []
    for rec in published:
        pub_date = datetime.fromisoformat(rec["published_at"]).date()
        end = min(pub_date + timedelta(days=args.days), today)
        metrics = query_video(service, rec["video_id"], pub_date.isoformat(), end.isoformat())
        results.append({
            "video_id": rec["video_id"],
            "title": rec["title"],
            "language": rec.get("language"),
            "render_dir": rec.get("render_dir"),
            "published_at": rec["published_at"],
            "window_days": (end - pub_date).days,
            "metrics": metrics,
            # Analytics API 미제공 — YouTube Studio에서 수동 입력
            "impressions": None,
            "ctr": None,
        })
        print(f"수집: {rec['title']} → {metrics or '데이터 없음'}", file=sys.stderr)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{today.isoformat()}-d{args.days}.json"
    out_path.write_text(json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(), "window_days": args.days, "videos": results},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n영상 {len(results)}건 → {out_path}")
    print("주의: impressions/ctr은 API 미제공 — Studio에서 확인해 수동 보충 필요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
