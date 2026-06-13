# 대본 생성 모드 가이드 — 스타일 × 길이

영상 제작에 비주얼 타입(`docs/video-production.md`)이 있듯, 대본도 **스타일(톤·구조)과 길이(포맷)**를 골라 쓴다.
정의: `config/script-modes.yaml` · 해석기: `scripts/script_mode.py`

```bash
python scripts/script_mode.py --list                       # 목록
python scripts/script_mode.py --style mystery --format short  # 사양 출력
```

어떤 조합이든 **불변 규칙**은 유지된다: 모든 주장은 `sources/facts.md`의 `[S##]`에 근거(claims.md 추적), 용어집 준수, script-critic 게이트 통과 후 제작.

## 스타일 (style) — 4종

| 스타일 | 한 줄 | 적합한 주제 | 핵심 구조 |
|---|---|---|---|
| `documentary` (기본) | 다큐 정통 — 차분히 사실을 쌓아 의미로 닫음 | 거의 모든 역사 주제 | 훅 → 회상 맥락 → 본문 블록 → 큰 그림 |
| `mystery` | 미스터리 추적형 — 질문을 던지고 단서를 추적 | 미해결·논쟁·반전이 있는 사건 | 수수께끼 → 단서 → 반전 → 진실 → 의미 |
| `first-person` | 인물 1인칭 — 한 사람의 눈으로 체험 | 강한 인물·드라마가 있는 사건 | 결정적 순간 → 회상 → 그의 시선 전개 → 줌아웃 |
| `listicle` | 리스트형 — "N가지" 미니 스토리 묶음 | 유입·입문, 사례가 여럿인 주제 | 훅(N 예고) → 항목1…N → 종합 의미 |

주의:
- **1인칭**은 사료 밖 심리·대사를 단정하지 말 것 — 추측은 "~했을 것입니다"로(claims 추적 유지).
- **리스트형**은 각 항목도 사실 근거·작은 스토리 필수(나열은 슬롭).

## 길이·포맷 (format) — 3종

| 포맷 | 길이 | 글자수 | 블록 | 시니어 레이어 | 용도 |
|---|---|---|---|---|---|
| `long` (기본) | 8~10분 | 2400~3000 | 4~6 | 전면 | 메인 표준, 광고 수익 유리 |
| `mid` | 3~5분 | 900~1500 | 3~4 | 전면 | 단일 사건·개념, 입문 |
| `short` | 0.5~1분 | 150~320 | 1~2 | **약화(속도 우선)** | 9:16 쇼츠, 유입 미끼 → 롱폼 유도 |

쇼츠는 도입·맥락을 생략하고 첫 1~2초에 훅, 용어 풀이는 꼭 필요한 1개만, 끝에 롱폼 연결 1문장.

## 조합 예시

| 목적 | 조합 |
|---|---|
| 메인 영상 (표준) | `documentary` × `long` |
| 몰입형 대표작 | `first-person` × `long` |
| 신규 유입·입문 | `mystery` 또는 `listicle` × `mid` |
| 알고리즘 유입 미끼 | `mystery` 또는 `listicle` × `short` |

## 사용 흐름

1. 스타일·포맷 결정 (또는 `modes/`의 검증된 모드 사용)
2. `/produce <topic> --style <style> --format <format>` 또는 scriptwriter가 `script_mode.py`로 사양 로드
3. draft 상단에 `<!-- mode: <style> × <format> -->` 기록 → script-critic이 그 기준으로 채점
4. 통과·발행 후 잘 통한 조합은 `modes/`에 저장 → mode-improver가 성과로 갱신

> 새 스타일·포맷이 필요하면 `config/script-modes.yaml`에 항목을 추가하면 즉시 사용 가능하다(코드 수정 불필요).
