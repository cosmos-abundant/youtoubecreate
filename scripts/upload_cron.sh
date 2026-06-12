#!/usr/bin/env bash
# upload-cron 실행 단위: 한/영 채널 폴더에서 미발행분을 1개씩 업로드한다.
# crontab 등록 예 (매일 09:00 한국어, 21:00 영어 — 간격을 두는 이유: 스팸 정책 회피·자연스러운 발행 패턴):
#   0 9  * * *  cd /path/to/youtube-factory && ./scripts/upload_cron.sh ko >> logs/upload.log 2>&1
#   0 21 * * *  cd /path/to/youtube-factory && ./scripts/upload_cron.sh en >> logs/upload.log 2>&1
set -euo pipefail

LANG_CODE="${1:?사용법: upload_cron.sh <ko|en> [privacy]}"
PRIVACY="${2:-private}"   # 운영 안정화 전까지 private 권장 (육안 확인 후 공개 전환)

cd "$(dirname "$0")/.."
mkdir -p logs

echo "[$(date -u +%FT%TZ)] upload-cron 시작: lang=${LANG_CODE} privacy=${PRIVACY}"
python3 scripts/upload_youtube.py --watch "library/renders/${LANG_CODE}" --max 1 --privacy "${PRIVACY}"
echo "[$(date -u +%FT%TZ)] upload-cron 종료"
