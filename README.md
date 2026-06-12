# YouTube Factory — 지식을 영상자산으로 변환하는 생산설비

영상 1개를 만드는 프로젝트가 아니다. **에버그린 지식 영상을 복리로 찍어내는 자본재(자동화 시스템)**를 만든다.

- 니치: 역사 · 과학 · 우주 · 사회 (고전·학술·공공자료가 풍부한 영역)
- 스타일: 전 연령 에버그린 주제 + **시니어 친화 전달 레이어** (고CPM·고시청지속)
- 운영 규칙: [CLAUDE.md](CLAUDE.md) — 저작권 가드레일, AI 슬롭 차단, LLM vs 코드 경계

## 파이프라인

```
topic-scout → researcher → scriptwriter ⇄ script-critic → video-producer → thumbnail-meta → upload
   (주제검증)    (사실수집)      (작성)        (품질게이트)       (제작)         (패키징)      (발행)
                                                                    ↘ 성과 학습 → modes/ (모드 저장·개선)
```

## 폴더 구조

| 경로 | 역할 |
|---|---|
| `.claude/agents/` | 서브에이전트 9종 (topic-scout, researcher, scriptwriter, script-critic, video-producer, thumbnail-meta, orchestrator, book-to-scripts, mode-improver) |
| `.claude/skills/` | 서적 전략 코드화 스킬 4종 (made-to-stick, influence-cialdini, hook-retention, senior-friendly) |
| `.claude/commands/` | `/produce` — 파이프라인 1회 실행 진입점 |
| `scripts/` | 결정론적 도구 — `yt_subtitles.py`, `outlier_score.py`, `upload_youtube.py`, `fetch_analytics.py`, `upload_cron.sh` |
| `config/` | `channel.yaml` (채널 아이덴티티 — 역사산책), `seed-channels.yaml` (인간 큐레이션 시드), `glossary.md` (용어집) |
| `docs/` | 운영 문서 — `channel-rebrand.md` (리브랜딩 체크리스트) |
| `sources/` | 출처 태그가 달린 사실 리소스 풀 |
| `modes/` | 검증된 모드 스냅샷 — **자본재의 핵심** |
| `library/` | 산출물: topics / scripts / renders(ko·en) / published.json |

## 시작하기 (Phase 1 MVP)

```bash
pip install -r requirements.txt

# 1. config/seed-channels.yaml 에 시드 채널 10~30개 등록 (enabled: true)
# 2. 아웃라이어 스캔
python scripts/outlier_score.py
# 3. Claude Code에서 파이프라인 실행
#    "orchestrator로 _candidates.json에서 주제 1개를 검증하고 대본까지 진행해줘"
# 4. (Phase 1은 영상화·업로드 수동) 발행 후 첫 모드를 modes/에 저장
```

파이프라인 실행은 Claude Code에서 `/produce` (또는 `/produce <topic-slug>`).

## 영상 제작 (로컬 실행 — 결과물은 `library/renders/<lang>/<slug>/`에 저장)

시스템 요구: **ffmpeg** + 한글 폰트(리눅스만 `fonts-nanum` 설치 필요). 이후:

```bash
# 1. 씬 구성 시안 생성 → scenes.json의 card_text/image 검토·수정
python scripts/produce_video.py library/scripts/<slug>/draft-v2.md --scenes-only

# 2. TTS(edge-tts, 무료) + 렌더 → final.mp4
python scripts/produce_video.py library/scripts/<slug>/draft-v2.md

# 3. 썸네일 합성
python scripts/make_thumbnail.py library/renders/ko/<slug> --text "후킹 문구"

# 4. assets.md에 사용 이미지·BGM 라이선스 전 항목 기입 (발행 게이트)
```

영상·오디오·썸네일은 용량 문제로 git에 올리지 않는다(scenes.json·assets.md만 추적). 같은 명령으로 언제든 재생성 가능.

## 업로드 자동화 (Phase 2+)

OAuth 클라이언트(`client_secrets.json`)를 준비하고 채널 계정별(ko/en)로 1회 인증:

```bash
python scripts/upload_youtube.py library/renders/ko/<slug> --dry-run   # 검증
python scripts/upload_youtube.py library/renders/ko/<slug>            # 단일 업로드 (기본 private)
./scripts/upload_cron.sh ko                                            # 미발행분 1개 업로드

# crontab 등록 (한/영 채널 시차 발행)
# 0 9  * * *  cd /path/to/repo && ./scripts/upload_cron.sh ko >> logs/upload.log 2>&1
# 0 21 * * *  cd /path/to/repo && ./scripts/upload_cron.sh en >> logs/upload.log 2>&1
```

렌더 폴더에 `thumbnail.png`가 있으면 자동 적용되고, 결과는 `library/published.json`에 기록된다.

## 개선 루프 (Phase 4)

```bash
python scripts/fetch_analytics.py --days 7    # 성과 데이터 회수 → library/analytics/
# Claude Code: "mode-improver로 이번 주 성과를 진단하고 모드를 업데이트해줘"
```

CTR·노출수는 Analytics API가 제공하지 않으므로 YouTube Studio에서 확인해 수동 보충한다.

## 테스트

```bash
python3 -m unittest discover tests -v
```

## 빌드 로드맵

| 단계 | 목표 |
|---|---|
| Phase 1 (MVP) | 영상 1개 끝까지 + 첫 모드 저장 — 수동 오케스트레이션 |
| Phase 2 | video-producer · thumbnail-meta · upload-cron 연결, 모드 2~3개 |
| Phase 3 | orchestrator + cron으로 한/영 동시 배치 발행 |
| Phase 4 | 개선 에이전트가 성과 데이터로 모드 업데이트 (자기개선 복리) |
