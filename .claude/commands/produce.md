---
description: 파이프라인 1회 실행 — 주제 검증부터 발행 준비까지 orchestrator로 진행
argument-hint: [topic-slug 또는 비워두면 후보에서 자동 선택]
---

orchestrator 서브에이전트로 파이프라인을 1회 실행하라. 대상: $ARGUMENTS (비어 있으면 `library/topics/_candidates.json`과 `library/topics/`에서 가장 유망한 미착수 주제 1개를 선택).

orchestrator의 표준 실행 순서와 게이트를 그대로 따르되:
1. 이미 완료된 단계의 산출물이 있으면 건너뛰지 말고 형식 검증 후 이어서 진행
2. 적용 가능한 `modes/`의 default/validated 모드가 있으면 우선 적용
3. script-critic 게이트(48/60, 불합격 조건 0건) 통과 전에는 절대 제작 단계로 넘어가지 말 것
4. Phase 1 환경(영상화 도구 미연결)이면 제작 단계에서 멈추고, video-producer 인계문까지 정리해 보고
5. 종료 시 보고: 진행 단계, 게이트 점수, 산출물 경로, 다음에 사람이 할 일
