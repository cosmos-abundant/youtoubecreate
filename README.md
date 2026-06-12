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
| `.claude/agents/` | 서브에이전트 8종 (topic-scout, researcher, scriptwriter, script-critic, video-producer, thumbnail-meta, orchestrator, book-to-scripts) |
| `.claude/skills/` | 서적 전략 코드화 스킬 4종 (made-to-stick, influence-cialdini, hook-retention, senior-friendly) |
| `scripts/` | 결정론적 도구 — `yt_subtitles.py`, `outlier_score.py`, `upload_youtube.py` |
| `config/` | `seed-channels.yaml` (인간 큐레이션 시드), `glossary.md` (용어집) |
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

업로드 자동화(Phase 2+)는 OAuth 클라이언트(`client_secrets.json`) 준비 후:

```bash
python scripts/upload_youtube.py library/renders/ko/<slug> --dry-run
python scripts/upload_youtube.py --watch library/renders/ko --max 1   # cron 등록용
```

## 빌드 로드맵

| 단계 | 목표 |
|---|---|
| Phase 1 (MVP) | 영상 1개 끝까지 + 첫 모드 저장 — 수동 오케스트레이션 |
| Phase 2 | video-producer · thumbnail-meta · upload-cron 연결, 모드 2~3개 |
| Phase 3 | orchestrator + cron으로 한/영 동시 배치 발행 |
| Phase 4 | 개선 에이전트가 성과 데이터로 모드 업데이트 (자기개선 복리) |
