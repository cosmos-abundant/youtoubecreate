# 영상 제작 가이드 — 4가지 방식과 상황별 배합

커뮤니티 검증 방식을 차용해 구성했다:
- **MoneyPrinterTurbo 방식** ([harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)): LLM 대본 → 씬별 검색어 → Pexels/Pixabay 스톡 → edge-TTS → 자동 자막 → ffmpeg 조립 + BGM. → 우리의 `stock` 타입 + 자막·BGM 기본기로 이식.
- **하이퍼프레임식 (AI 이미지 시퀀스)**: 씬별 AI 생성 이미지 + 켄번즈 모션. 역사 재현 장면의 표준. → `ai-image` 타입.
- **MCP/API 호출형**: Kling·Veo·Hailuo 등 영상 생성 모델을 MCP로 호출 ([mcp-kling](https://github.com/199-mcp/mcp-kling), [mcp-video-gen](https://github.com/kevinten-ai/mcp-video-gen), fal.ai 단일 키로 600+ 모델). → `ai-video` 타입.
- 이 모든 걸 **씬 단위로 섞는다** — 타입 정의·프리셋: `config/video-modes.yaml`.

## 역할 분담 (LLM vs 코드 경계 유지)

| 단계 | 담당 |
|---|---|
| 씬별 비주얼 타입·프롬프트·검색어·모션 선택 | **video-producer 에이전트** (판단) |
| AI 이미지·영상 생성 (MCP/API 호출) | **에이전트** → 결과 파일을 `genai/scene-XX.*`에 배치 |
| 스톡 검색·다운로드·출처 기록 | 코드 (`fetch_stock.py` — visual.query만 있으면 렌더 중 자동) |
| TTS·모션·자막·페이드·조립 | 코드 (`produce_video.py`) |

## scenes.json 비주얼 스키마

```json
{
  "id": 5,
  "visual": {
    "type": "ai-image",            // card | stock | ai-image | ai-video | file
    "file": "genai/scene-05.png",  // stock은 query만으로 자동 다운로드 가능
    "query": null,                  // stock용 검색어 (영어)
    "prompt": "1898 Korean palace, official bowing to wall telephone, sepia documentary still",
    "motion": "zoom-in"             // zoom-in | zoom-out | pan-left | pan-right | none
  }
}
```

## 상황별 선택 기준 (영상미 × 비용)

| 씬 상황 | 타입 | 이유 |
|---|---|---|
| 훅·클라이맥스 (가장 강한 그림이 필요) | ai-image (성과 검증작은 ai-video 1~2씬) | 주목도가 리텐션을 결정 |
| 역사 재현 (인물·복식·시대) | ai-image | 스톡은 시대 불일치 위험 |
| 보편 사물·풍경 (전화기, 바다, 옛 거리) | stock | 무료·실사 질감 |
| 챕터 전환·연도·인용구 | card | 리듬 환기 + 비용 0 |
| 퍼블릭 도메인 사진·그림이 존재 | file | 진본 > 생성물 (신뢰 신호) |

규칙:
1. **5씬 연속 같은 타입 금지** — 시각 리듬이 죽는다.
2. 모션은 줌인/줌아웃 교차가 기본값(자동), 감정 고조 씬은 zoom-in 고정.
3. 실존 인물 AI 생성은 초상 왜곡 주의 — 인물 클로즈업 대신 뒷모습·실루엣·장면 위주.
4. 생성 프롬프트·모델명을 assets.md에 기록 (stock은 stock-credits.json 자동 기록).

## API·MCP 연결

| 용도 | 설정 |
|---|---|
| 스톡 | 환경변수 `PEXELS_API_KEY`(pexels.com/api), `PIXABAY_API_KEY` — 무료 |
| AI 이미지 | fal.ai 등 API 또는 이미지 생성 MCP 서버 → 에이전트가 호출 |
| AI 영상 | mcp-kling / mcp-video-gen / fal.ai (Veo·Kling·Hailuo) → 에이전트가 호출 |
| TTS 업그레이드 | 슈퍼톤·ElevenLabs API 키 확보 시 produce_video.py `_synthesize`에 어댑터 추가 |

Claude Code에 MCP 서버 등록: `claude mcp add <name> ...` 후 video-producer가 세션에서 직접 생성 호출.

## BGM

- 라이선스 확인된 트랙만 (`--bgm 파일`) — YouTube 오디오 라이브러리(무료) 권장.
- -18dB 자동 믹스. 트랙·출처를 assets.md에 기입.

## 품질 점검 (발행 전)

- [ ] 모바일 화면에서 자막 판독 가능한가 (기본 스타일은 시니어 가독 기준)
- [ ] 훅 씬의 그림이 썸네일과 톤 일치하는가 (배신 금지)
- [ ] 시각 리듬: 같은 타입 5씬 연속 없음, 모션 단조롭지 않음
- [ ] assets.md 라이선스 전 항목 기입
