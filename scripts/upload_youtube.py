#!/usr/bin/env python3
"""YouTube Data API 업로드 도구 (upload-cron의 실행 단위).

library/renders/<ko|en>/<slug>/ 디렉터리에서 final.mp4 + meta.json 을 읽어 업로드하고,
성공 시 library/published.json 에 기록한다. cron에서 --watch 모드로 폴더를 순회시킨다.

사용:
    python scripts/upload_youtube.py <render_dir>            # 단일 업로드
    python scripts/upload_youtube.py --watch library/renders/ko --max 1   # cron용: 미발행분 중 1개 업로드
    python scripts/upload_youtube.py <render_dir> --dry-run  # 검증만

인증 (한/영 채널 분리):
    client_secrets.json (OAuth 클라이언트) + 채널 계정별 최초 1회 브라우저 인증
    → .credentials/token-<lang>.json 캐시 (meta.json의 language가 어느 채널 토큰을 쓸지 결정)
    환경변수 YT_CLIENT_SECRETS 로 클라이언트 파일 경로 재정의 가능.

썸네일: 렌더 디렉터리에 thumbnail.png 또는 thumbnail.jpg 가 있으면 업로드 후 자동 적용.

요구: pip install google-api-python-client google-auth-oauthlib
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
PUBLISHED_PATH = Path("library/published.json")
CATEGORY_IDS = {"education": "27", "people": "22", "science": "28", "entertainment": "24"}


def load_meta(render_dir: Path) -> tuple[Path, dict]:
    video = render_dir / "final.mp4"
    meta_path = render_dir / "meta.json"
    if not video.exists():
        raise FileNotFoundError(f"영상 없음: {video}")
    if not meta_path.exists():
        raise FileNotFoundError(f"메타 없음: {meta_path} (thumbnail-meta 단계 미완료)")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in ("title_final", "description"):
        if not meta.get(key):
            raise ValueError(f"meta.json에 '{key}' 누락")
    return video, meta


def load_published() -> list[dict]:
    if PUBLISHED_PATH.exists():
        return json.loads(PUBLISHED_PATH.read_text(encoding="utf-8"))
    return []


def save_published(records: list[dict]) -> None:
    PUBLISHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLISHED_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def get_service(lang: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    secrets = Path(os.environ.get("YT_CLIENT_SECRETS", "client_secrets.json"))
    token_path = Path(f".credentials/token-{lang}.json")
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secrets.exists():
                raise FileNotFoundError(f"OAuth 클라이언트 파일 없음: {secrets}")
            print(f"'{lang}' 채널 계정으로 브라우저 인증을 진행하세요.", file=sys.stderr)
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def find_thumbnail(render_dir: Path) -> Path | None:
    for name in ("thumbnail.png", "thumbnail.jpg"):
        p = render_dir / name
        if p.exists():
            return p
    return None


def upload(render_dir: Path, privacy: str, dry_run: bool) -> dict | None:
    video, meta = load_meta(render_dir)
    lang = meta.get("language", "ko")
    body = {
        "snippet": {
            "title": meta["title_final"],
            "description": meta["description"],
            "tags": meta.get("tags", []),
            "categoryId": CATEGORY_IDS.get(str(meta.get("category", "education")).lower(), "27"),
            "defaultLanguage": lang,
            "defaultAudioLanguage": lang,
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }

    if dry_run:
        print(f"[dry-run] 업로드 대상 검증 통과: {video}")
        thumb = find_thumbnail(render_dir)
        print(f"[dry-run] 썸네일: {thumb or '없음 (자동 생성 썸네일 사용됨 — 권장하지 않음)'}")
        print(json.dumps(body["snippet"] | {"description": body['snippet']['description'][:80] + "…"},
                         ensure_ascii=False, indent=2))
        return None

    from googleapiclient.http import MediaFileUpload

    service = get_service(lang)
    media = MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  업로드 {int(status.progress() * 100)}%", file=sys.stderr)

    thumb = find_thumbnail(render_dir)
    if thumb:
        service.thumbnails().set(videoId=response["id"], media_body=MediaFileUpload(str(thumb))).execute()
        print(f"  썸네일 적용: {thumb.name}", file=sys.stderr)
    else:
        print("  경고: thumbnail.png/jpg 없음 — 자동 생성 썸네일 사용됨", file=sys.stderr)

    record = {
        "video_id": response["id"],
        "url": f"https://www.youtube.com/watch?v={response['id']}",
        "title": meta["title_final"],
        "language": lang,
        "render_dir": str(render_dir),
        "privacy": privacy,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    print(f"업로드 완료: {record['url']}")
    return record


def find_pending(watch_dir: Path, published: list[dict]) -> list[Path]:
    done = {r["render_dir"] for r in published}
    pending = []
    for meta_path in sorted(watch_dir.glob("*/meta.json")):
        d = meta_path.parent
        if str(d) not in done and (d / "final.mp4").exists():
            pending.append(d)
    return pending


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube 업로드 (단일 또는 cron watch 모드)")
    parser.add_argument("render_dir", nargs="?", help="library/renders/<lang>/<slug>/ 경로")
    parser.add_argument("--watch", help="미발행분을 찾을 디렉터리 (예: library/renders/ko)")
    parser.add_argument("--max", type=int, default=1, help="watch 모드에서 회당 업로드 수 (기본 1)")
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"],
                        help="기본 private — 발행 전 최종 육안 확인 후 공개 전환 권장")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    published = load_published()
    if args.watch:
        targets = find_pending(Path(args.watch), published)[: args.max]
        if not targets:
            print("발행 대기 영상 없음.")
            return 0
    elif args.render_dir:
        targets = [Path(args.render_dir)]
    else:
        parser.error("render_dir 또는 --watch 필요")

    failures = 0
    for d in targets:
        try:
            record = upload(d, args.privacy, args.dry_run)
        except Exception as e:
            print(f"실패: {d} — {e}", file=sys.stderr)
            failures += 1
            continue
        if record:
            published.append(record)
            save_published(published)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
