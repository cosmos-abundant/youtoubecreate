#!/usr/bin/env python3
"""대본 문체 린트 — 낭독 리듬·어미·전환어를 결정론적으로 계측.

AI 슬롭의 핵심 신호는 '균일한 문장'이다. 사람은 문장 길이와 종결을 변주하지만,
LLM은 비슷한 길이·비슷한 어미·일정한 쉼표 패턴을 반복하는 경향이 있다. 텍스트를
눈으로 봐선 잘 안 띄는 이 패턴을 수치로 드러내, script-critic의 게이트 6(AI스러움)을
객관적으로 보조한다. (통과/실패 판정은 critic의 몫 — 이 도구는 신호만 제공한다.)

사용:
    python scripts/script_lint.py library/scripts/<slug>/draft-v2.md [--json]

요구: 표준 라이브러리만.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

# 용어집 금지규칙 기반 기계적 전환어·상투어 (문두 또는 단독 등장 시 신호)
FILLERS = [
    "그런데", "한편", "그리고 ", "하지만 ", "또한", "자,", "자 그럼", "그럼",
    "놀랍게도", "충격적이게도", "사실", "결국", "과연", "바로", "이처럼", "이렇게",
    "어떻게 보면", "말하자면", "다름 아닌",
]
# 과장 최상급 (근거 없을 때 슬롭 신호 — critic이 facts와 대조)
SUPERLATIVES = ["역사상 가장", "전 세계가", "최초로", "유일한", "그 누구도"]


def load_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)   # scene/mode 주석 제거
    raw = re.sub(r"^#.*$", "", raw, flags=re.MULTILINE)      # 마크다운 heading 제거
    return raw.strip()


def split_sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?…])\s+", flat)
    return [p.strip() for p in parts if p.strip()]


def ending(sent: str) -> str:
    """문장의 종결부(구두점 제외 마지막 4글자)를 어미 키로."""
    s = re.sub(r"[\".!?…’”\)\s]+$", "", sent)
    return s[-4:] if len(s) >= 4 else s


def max_run(seq: list[str]) -> tuple[int, str]:
    best, best_key, cur, cur_key = 0, "", 0, None
    for x in seq:
        if x == cur_key:
            cur += 1
        else:
            cur, cur_key = 1, x
        if cur > best:
            best, best_key = cur, x
    return best, best_key


def analyze(text: str) -> dict:
    sents = split_sentences(text)
    n = len(sents)
    lengths = [len(re.sub(r"\s", "", s)) for s in sents]
    endings = [ending(s) for s in sents]
    end_run, end_run_key = max_run(endings)
    end_counter = Counter(endings)
    top_end, top_end_n = end_counter.most_common(1)[0] if end_counter else ("", 0)

    commas = [s.count(",") + s.count("，") for s in sents]
    comma_sentences = sum(1 for c in commas if c > 0)

    body = text
    fillers = {f.strip(): len(re.findall(re.escape(f), body)) for f in FILLERS}
    fillers = {k: v for k, v in fillers.items() if v}
    superl = {s: len(re.findall(re.escape(s), body)) for s in SUPERLATIVES}
    superl = {k: v for k, v in superl.items() if v}

    mean_len = statistics.mean(lengths) if lengths else 0
    stdev_len = statistics.pstdev(lengths) if len(lengths) > 1 else 0
    cv = (stdev_len / mean_len) if mean_len else 0

    short_ratio = sum(1 for l in lengths if l <= 15) / n if n else 0
    long_ratio = sum(1 for l in lengths if l >= 40) / n if n else 0

    warnings = []
    if cv < 0.45:
        warnings.append(f"문장 길이가 단조롭다 (변동계수 {cv:.2f} < 0.45) — 길이 변주 필요")
    if end_run >= 3:
        warnings.append(f"같은 어미 '{end_run_key}'가 {end_run}문장 연속 — 종결 변주 필요")
    if n and top_end_n / n > 0.35:
        warnings.append(f"한 어미 '{top_end}'가 전체의 {top_end_n/n:.0%} — 종결 다양화 필요")
    if n and comma_sentences / n > 0.8:
        warnings.append(f"문장의 {comma_sentences/n:.0%}에 쉼표 — 쉼표 호흡 패턴이 기계적")
    if short_ratio > 0.85:
        warnings.append(f"짧은 문장(≤15자)이 {short_ratio:.0%} — 짧음≠좋음, 긴 호흡 문장도 섞을 것")
    total_fillers = sum(fillers.values())
    if total_fillers >= 6:
        warnings.append(f"기계적 전환어 {total_fillers}건 — {', '.join(f'{k}×{v}' for k,v in fillers.items())}")
    if superl:
        warnings.append(f"최상급 표현 {sum(superl.values())}건 (근거 확인): {', '.join(superl)}")

    return {
        "sentences": n,
        "mean_len": round(mean_len, 1),
        "stdev_len": round(stdev_len, 1),
        "cv": round(cv, 2),
        "min_len": min(lengths) if lengths else 0,
        "max_len": max(lengths) if lengths else 0,
        "short_ratio": round(short_ratio, 2),
        "long_ratio": round(long_ratio, 2),
        "top_ending": top_end,
        "top_ending_ratio": round(top_end_n / n, 2) if n else 0,
        "max_same_ending_run": end_run,
        "comma_sentence_ratio": round(comma_sentences / n, 2) if n else 0,
        "fillers": fillers,
        "superlatives": superl,
        "warnings": warnings,
    }


def format_report(a: dict, name: str) -> str:
    L = [f"# 대본 린트: {name}", ""]
    L.append(f"- 문장 수: {a['sentences']}")
    L.append(f"- 길이(공백 제외): 평균 {a['mean_len']}자, 표준편차 {a['stdev_len']}, "
             f"변동계수(CV) {a['cv']}  [최소 {a['min_len']} / 최대 {a['max_len']}]")
    L.append(f"- 짧은 문장(≤15자) {a['short_ratio']:.0%} · 긴 문장(≥40자) {a['long_ratio']:.0%}")
    L.append(f"- 최빈 어미 '{a['top_ending']}' {a['top_ending_ratio']:.0%} · 같은 어미 최대 연속 {a['max_same_ending_run']}")
    L.append(f"- 쉼표 포함 문장 {a['comma_sentence_ratio']:.0%}")
    if a["fillers"]:
        L.append(f"- 전환어: {', '.join(f'{k}×{v}' for k,v in a['fillers'].items())}")
    L.append("")
    if a["warnings"]:
        L.append("## ⚠ 신호 (critic 게이트 6 참고)")
        for w in a["warnings"]:
            L.append(f"- {w}")
    else:
        L.append("## 신호 없음 — 리듬·종결·전환어 양호")
    L.append("")
    L.append("참고 기준(가이드): CV≥0.45, 같은 어미 연속<3, 최빈 어미<35%, 쉼표 문장<80%.")
    return "\n".join(L)


def main() -> int:
    p = argparse.ArgumentParser(description="대본 문체 린트 (낭독 리듬·어미·전환어 계측)")
    p.add_argument("draft", help="대본 .md 경로")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    path = Path(args.draft)
    if not path.exists():
        print(f"오류: 파일 없음 — {path}", file=sys.stderr)
        return 1
    a = analyze(load_text(path))
    print(json.dumps(a, ensure_ascii=False, indent=2) if args.json else format_report(a, path.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
