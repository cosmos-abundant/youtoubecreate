---
description: 파이프라인 1회 실행 — 주제 검증부터 발행 준비까지 orchestrator로 진행
argument-hint: [topic-slug] [--style documentary|mystery|first-person|listicle] [--format long|mid|short]
---

orchestrator 서브에이전트로 파이프라인을 1회 실행하라. 인자: $ARGUMENTS

인자 파싱:
- 첫 비옵션 토큰 = topic-slug (비어 있으면 `library/topics/_candidates.json`과 `library/topics/`에서 가장 유망한 미착수 주제 1개를 선택).
- `--style` / `--format` = 대본 모드. 생략 시 적용 모드의 값, 그것도 없으면 기본값(documentary × long). scriptwriter·script-critic에 그대로 전달한다 (`config/script-modes.yaml`).

orchestrator의 표준 실행 순서와 게이트를 그대로 따르되:
1. 이미 완료된 단계의 산출물이 있으면 건너뛰지 말고 형식 검증 후 이어서 진행
2. 적용 가능한 `modes/`의 default/validated 모드가 있으면 우선 적용 (스타일·포맷 포함)
3. scriptwriter는 작업 전 `python scripts/script_mode.py --style <> --format <>`로 사양을 받아 따른다
4. script-critic 게이트(48/60, 불합격 조건 0건) 통과 전에는 절대 제작 단계로 넘어가지 말 것
5. Phase 1 환경(영상화 도구 미연결)이면 제작 단계에서 멈추고, video-producer 인계문까지 정리해 보고
6. 종료 시 보고: 적용 모드(스타일×포맷), 진행 단계, 게이트 점수, 산출물 경로, 다음에 사람이 할 일
