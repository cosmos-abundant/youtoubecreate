# 제작 단계 인계문 — deokryulpung-first-telephone

> Phase 1 (수동 오케스트레이션) 정지 지점. 대본 파이프라인은 완료, 영상화부터는 사람/Phase 2 작업.

## 상태

- **확정 대본**: `draft-v2.md` (script-critic **통과 55/60**, 불합격 조건 0건 — `review-v2.md`)
- 인계 전 필수 수정 1건(§3 "그중 한 대는" → "초기 에릭슨 전화기 한 대는") **반영 완료** (orchestrator가 diff 적용, 비평가 재심 갈음 조건)
- claims.md [S21] 정리 권장사항 반영 완료
- 분량: 공백 제외 약 2,540자 ≈ 낭독 8.5분
- 패키징 재료: `packaging.md` (가제 3종, 썸네일 A/B, 후킹 키워드)

## 발행 전 필수사항 (review-v2.md 상세)

| # | 항목 | 담당 |
|---|---|---|
| 1 | [S07] 수치(전화 요금 5분 50전·10분 제한) 원문 대조 | researcher/사람 |
| 2 | [S03] 최고(最古) 통화 기록 원문 재확인 (수집이 검색 요약 기반이었음) | researcher/사람 |
| 3 | 편집 시 단일출처 헤지 문구("~고 전합니다" 등) 삭제 금지 | video-producer |
| 4 | TTS 실측 길이 확인 — 9분 초과 시에만 추가 절단 (절단 후보는 review-v2 참조) | video-producer |
| 5 | 씬 자료(사진·일러스트) 라이선스 확인 + `assets.md` 기록 — 저작권 가드레일 | video-producer |
| 6 | (선택) 50전 구매력·고종 승하 월일의 기관 출처 확보 시 보강 | researcher |

## 다음 단계 (사람)

1. TTS 모드 선택(기본 추천/슈퍼톤 등) 후 video-producer 실행 → `library/renders/ko/deokryulpung-first-telephone/`
2. thumbnail-meta 실행 → `meta.json` + `thumbnail.png`
3. 업로드(`scripts/upload_youtube.py <dir> --dry-run` 검증 후) — 기본 private, 육안 확인 후 공개
4. **발행 완료 시 반드시 `modes/`에 첫 모드 스냅샷 저장** (`modes/_template.yaml`) — 이번 시운전에서 검증된 설정: 8분 역사물 / 추천각도 "기술+인간서사" / 5블록 피히테 구조 / 액자식 논쟁 처리 / 클라이맥스 마지막 1/3 배치

## 시운전 메모 (시스템 개선 입력)

- 게이트가 실제로 작동: v1 47/60 재작성(위키 단독 출처 적발) → v2 55/60 통과. 비평가가 v2에서 신규 결함("그중 한 대는" 동일성 단정)도 잡아냄 — 퇴행 점검 항목이 유효함.
- researcher 환경 한계: 이 환경에서 원문 fetch가 차단되어 검색 요약 기반 수집 → 발행 전 원문 대조 단계가 필수로 추가됨. 로컬 운영 시에는 WebFetch 가능하므로 부담 감소 예상.
