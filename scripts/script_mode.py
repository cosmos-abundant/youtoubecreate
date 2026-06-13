#!/usr/bin/env python3
"""대본 생성 모드 해석기 (scriptwriter의 입력 사양 생성).

config/script-modes.yaml 의 스타일(톤·구조)과 포맷(길이)을 골라 병합한
"대본 사양"을 출력한다. scriptwriter 에이전트가 작업 시작 시 이 사양을 로드해
그대로 따른다. 영상 쪽 produce_video.py에 대응하는 결정론 도구.

사용:
    python scripts/script_mode.py                          # 기본값(documentary × long)
    python scripts/script_mode.py --style mystery --format short
    python scripts/script_mode.py --list                   # 가능한 스타일·포맷 목록
    python scripts/script_mode.py --style listicle --json   # 기계 판독용 JSON

요구: pip install pyyaml
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONFIG = Path("config/script-modes.yaml")


def load_config(path: Path = CONFIG) -> dict:
    import yaml

    if not path.exists():
        raise FileNotFoundError(f"설정 파일 없음: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve(cfg: dict, style: str | None, fmt: str | None) -> dict:
    """스타일+포맷을 검증·병합해 대본 사양 dict를 반환한다."""
    styles = cfg.get("styles", {})
    formats = cfg.get("formats", {})
    defaults = cfg.get("defaults", {})

    style = style or defaults.get("style", "documentary")
    fmt = fmt or defaults.get("format", "long")

    if style not in styles:
        raise ValueError(f"알 수 없는 스타일: '{style}'  (가능: {', '.join(styles)})")
    if fmt not in formats:
        raise ValueError(f"알 수 없는 포맷: '{fmt}'  (가능: {', '.join(formats)})")

    s, f = styles[style], formats[fmt]
    cautions = [c for c in (s.get("caution"), f.get("caution")) if c]
    return {
        "style_id": style,
        "format_id": fmt,
        "style_name": s.get("name", style),
        "format_name": f.get("name", fmt),
        "structure": s.get("structure", ""),
        "hook": s.get("hook", ""),
        "narration_person": s.get("narration_person", ""),
        "tone": s.get("tone", ""),
        "skill_emphasis": s.get("skill_emphasis", []),
        "target_min": f.get("target_min", []),
        "chars": f.get("chars", []),
        "blocks": f.get("blocks", []),
        "minihook_interval_sec": f.get("minihook_interval_sec"),
        "aspect": f.get("aspect", "16:9"),
        "senior_layer": f.get("senior_layer", "full"),
        "use": f.get("use", ""),
        "cautions": cautions,
    }


def _rng(v: list, unit: str) -> str:
    if isinstance(v, list) and len(v) == 2:
        return f"{v[0]}~{v[1]}{unit}"
    return f"{v}{unit}"


def format_spec(spec: dict) -> str:
    lines = [
        f"# 대본 사양: {spec['style_name']} × {spec['format_name']}",
        f"- 목표 길이: {_rng(spec['target_min'], '분')} (약 {_rng(spec['chars'], '자')}, 낭독 기준)",
        f"- 블록 수: {_rng(spec['blocks'], '개')}",
        f"- 구조: {spec['structure']}",
        f"- 훅: {spec['hook']}",
        f"- 화자: {spec['narration_person']}",
        f"- 톤: {spec['tone']}",
        f"- 강조 스킬: {', '.join(spec['skill_emphasis'])}",
        f"- 화면비: {spec['aspect']}  |  시니어 레이어: "
        + ("전면 적용" if spec["senior_layer"] == "full" else "약화(속도 우선)"),
    ]
    interval = spec["minihook_interval_sec"]
    if interval:
        lines.append(f"- 미니훅 간격: 약 {interval}초마다")
    elif spec["format_id"] == "short":
        lines.append("- 미니훅: 영상 전체가 하나의 훅 (도입·맥락 생략)")
    if spec["use"]:
        lines.append(f"- 용도: {spec['use']}")
    for c in spec["cautions"]:
        lines.append(f"- ⚠ 주의: {c}")
    lines.append("")
    lines.append("불변 규칙: 모든 주장은 sources/facts.md의 [S##]에 근거(claims.md 추적), "
                 "용어집 준수, script-critic 게이트 통과 후 제작.")
    return "\n".join(lines)


def list_modes(cfg: dict) -> str:
    out = ["## 스타일 (style)"]
    for k, v in cfg.get("styles", {}).items():
        mark = "  (기본값)" if k == cfg.get("defaults", {}).get("style") else ""
        out.append(f"- {k}{mark}: {v.get('name')} — {v.get('description', '')}")
    out.append("\n## 포맷 (format)")
    for k, v in cfg.get("formats", {}).items():
        mark = "  (기본값)" if k == cfg.get("defaults", {}).get("format") else ""
        out.append(f"- {k}{mark}: {v.get('name')} — {_rng(v.get('target_min', []), '분')} "
                   f"({_rng(v.get('chars', []), '자')})")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description="대본 생성 모드 해석기 (스타일 × 포맷)")
    p.add_argument("--style", default=None, help="대본 스타일 (예: documentary, mystery, first-person, listicle)")
    p.add_argument("--format", default=None, dest="fmt", help="영상 길이 (long, mid, short)")
    p.add_argument("--list", action="store_true", help="가능한 스타일·포맷 목록")
    p.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = p.parse_args()

    try:
        cfg = load_config()
        if args.list:
            print(list_modes(cfg))
            return 0
        spec = resolve(cfg, args.style, args.fmt)
    except (FileNotFoundError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1

    print(json.dumps(spec, ensure_ascii=False, indent=2) if args.json else format_spec(spec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
