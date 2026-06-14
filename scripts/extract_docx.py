#!/usr/bin/env python3
"""문서(.docx) → 마크다운 텍스트 변환 (book-to-scripts의 입력 준비).

.docx의 본문과 제목(heading) 구조를 살려 마크다운으로 변환한다. book-to-scripts
에이전트는 Read 도구로 텍스트만 읽을 수 있으므로, 바이너리 docx를 먼저 이 도구로
변환해 sources/books/<slug>/source.md 로 둔다 (파일 변환 = 코드 경계).

저작권: 변환 결과는 '리서치 인풋'이다. 원문 문장을 대본에 복제하지 않는다(CLAUDE.md).
        book-to-scripts는 사실·구조·인사이트만 추출해 독창적으로 재구성한다.

사용:
    python scripts/extract_docx.py <파일.docx> --slug soft-war
        [--out sources/books/<slug>/source.md] [--max-chars 0]

요구: 표준 라이브러리만 사용 (zipfile + xml). 추가 설치 불필요.
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# 이 문서군에서 outline 레벨로 쓰인 스타일명 → 마크다운 heading 레벨
HEADING_STYLES = {"1": 1, "2": 2, "3": 3, "Heading1": 1, "Heading2": 2, "Heading3": 3}


def docx_to_markdown(path: Path) -> tuple[str, dict]:
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read("word/document.xml").decode("utf-8", "replace"))
    lines: list[str] = []
    stats = {"paragraphs": 0, "headings": 0, "chars": 0}
    for p in root.iter(NS + "p"):
        style = ""
        pPr = p.find(NS + "pPr")
        if pPr is not None:
            ps = pPr.find(NS + "pStyle")
            if ps is not None:
                style = ps.get(NS + "val", "")
        text = "".join(t.text or "" for t in p.iter(NS + "t")).strip()
        if not text:
            continue
        text = re.sub(r"\s+", " ", text)
        stats["paragraphs"] += 1
        stats["chars"] += len(text)
        level = HEADING_STYLES.get(style)
        if level:
            stats["headings"] += 1
            lines.append("")
            lines.append("#" * level + " " + text)
            lines.append("")
        else:
            lines.append(text)
    md = "\n".join(lines).strip() + "\n"
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md, stats


def main() -> int:
    p = argparse.ArgumentParser(description="docx → 마크다운 (book-to-scripts 입력 준비)")
    p.add_argument("docx", help="입력 .docx 경로")
    p.add_argument("--slug", required=True, help="책 슬러그 (예: soft-war)")
    p.add_argument("--out", default=None, help="출력 경로 (기본 sources/books/<slug>/source.md)")
    p.add_argument("--max-chars", type=int, default=0, help="앞에서부터 N자만 (0=전체, 테스트 시 유용)")
    args = p.parse_args()

    src = Path(args.docx)
    if not src.exists():
        print(f"오류: 파일 없음 — {src}", file=sys.stderr)
        return 1
    try:
        md, stats = docx_to_markdown(src)
    except (zipfile.BadZipFile, KeyError) as e:
        print(f"오류: docx 파싱 실패 — {e}", file=sys.stderr)
        return 1

    if args.max_chars and len(md) > args.max_chars:
        md = md[:args.max_chars] + "\n\n[... 이후 생략 (--max-chars) ...]\n"

    out = Path(args.out) if args.out else Path("sources/books") / args.slug / "source.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"<!-- 출처 문서: {src.name} | 리서치 인풋 전용 — 원문 복제 금지 (CLAUDE.md) -->\n"
        f"<!-- 변환 통계: 문단 {stats['paragraphs']}개, heading {stats['headings']}개, "
        f"{stats['chars']:,}자 -->\n\n"
    )
    out.write_text(header + md, encoding="utf-8")
    print(f"저장: {out}")
    print(f"문단 {stats['paragraphs']}개 · heading {stats['headings']}개 · {stats['chars']:,}자")
    return 0


if __name__ == "__main__":
    sys.exit(main())
