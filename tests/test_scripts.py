"""scripts/ 결정론적 도구의 순수 함수 단위 테스트.

실행: python3 -m unittest discover tests -v
(네트워크·API 호출 없는 함수만 검증한다)
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import outlier_score
import produce_video
import script_mode
import upload_youtube
import yt_subtitles


class TestScriptMode(unittest.TestCase):
    def setUp(self):
        # 실제 config/script-modes.yaml로 검증 (저장소 루트 기준)
        root = Path(__file__).resolve().parent.parent
        self.cfg = script_mode.load_config(root / "config" / "script-modes.yaml")

    def test_defaults(self):
        spec = script_mode.resolve(self.cfg, None, None)
        self.assertEqual(spec["style_id"], "documentary")
        self.assertEqual(spec["format_id"], "long")
        self.assertEqual(spec["target_min"], [8, 10])

    def test_specific_combo(self):
        spec = script_mode.resolve(self.cfg, "mystery", "short")
        self.assertEqual(spec["style_name"], "미스터리 추적형")
        self.assertEqual(spec["aspect"], "9:16")
        self.assertEqual(spec["senior_layer"], "light")
        # 스타일·포맷 주의사항이 둘 다 병합됨
        self.assertEqual(len(spec["cautions"]), 2)

    def test_invalid_names_raise(self):
        with self.assertRaises(ValueError):
            script_mode.resolve(self.cfg, "nope", "long")
        with self.assertRaises(ValueError):
            script_mode.resolve(self.cfg, "documentary", "nope")

    def test_format_spec_text(self):
        text = script_mode.format_spec(script_mode.resolve(self.cfg, "listicle", "mid"))
        self.assertIn("리스트형 × 미드폼", text)
        self.assertIn("3~5분", text)
        self.assertIn("불변 규칙", text)

    def test_all_presets_resolve(self):
        for style in self.cfg["styles"]:
            for fmt in self.cfg["formats"]:
                spec = script_mode.resolve(self.cfg, style, fmt)
                self.assertTrue(spec["structure"])
                self.assertTrue(script_mode.format_spec(spec))


class TestOutlierScore(unittest.TestCase):
    THRESHOLDS = {"analyze": 3, "deep_dive": 8, "breakout": 25}

    def test_classify_tiers(self):
        self.assertIsNone(outlier_score.classify(2.9, self.THRESHOLDS))
        self.assertEqual(outlier_score.classify(3.0, self.THRESHOLDS), "analyze")
        self.assertEqual(outlier_score.classify(8.0, self.THRESHOLDS), "deep_dive")
        self.assertEqual(outlier_score.classify(25.0, self.THRESHOLDS), "breakout")
        self.assertEqual(outlier_score.classify(100.0, self.THRESHOLDS), "breakout")

    def test_within_window(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y%m%d")
        old = (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%Y%m%d")
        self.assertTrue(outlier_score.within_window(recent, 6))
        self.assertFalse(outlier_score.within_window(old, 6))
        # 날짜 정보가 없거나 깨졌으면 보수적으로 포함 (에이전트가 확인)
        self.assertTrue(outlier_score.within_window(None, 6))
        self.assertTrue(outlier_score.within_window("not-a-date", 6))


class TestYtSubtitles(unittest.TestCase):
    def test_vtt_to_text_strips_noise_and_dedupes(self):
        vtt = (
            "WEBVTT\nKind: captions\nLanguage: ko\n\n"
            "1\n00:00:01.000 --> 00:00:03.000\n안녕하세요 <c>여러분</c>\n\n"
            "2\n00:00:03.000 --> 00:00:05.000\n안녕하세요 여러분\n\n"
            "3\n00:00:05.000 --> 00:00:07.000\n오늘의   주제입니다\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".vtt", delete=False, encoding="utf-8") as f:
            f.write(vtt)
        text = yt_subtitles.vtt_to_text(Path(f.name))
        self.assertEqual(text, "안녕하세요 여러분\n오늘의 주제입니다")

    def test_slugify(self):
        self.assertEqual(yt_subtitles.slugify("Hello, World! 123"), "hello-world-123")
        self.assertEqual(yt_subtitles.slugify("   "), "untitled")
        self.assertLessEqual(len(yt_subtitles.slugify("a" * 200)), 60)


class TestProduceVideo(unittest.TestCase):
    DRAFT = (
        "# 제목\n\n"
        "<!-- scene: 1919년 홍릉, 상복의 황제 -->\n첫 씬 본문입니다.\n\n"
        "<!-- scene: 다이얼 전화, 교환원 -->\n둘째 씬 본문입니다.\n"
        "<!-- 일반 주석은 제거 -->\n이어지는 문장.\n"
    )

    def _write_draft(self, base: Path) -> Path:
        d = base / "topic-slug"
        d.mkdir(parents=True)
        p = d / "draft-v1.md"
        p.write_text(self.DRAFT, encoding="utf-8")
        return p

    def test_parse_scenes(self):
        with tempfile.TemporaryDirectory() as tmp:
            scenes = produce_video.parse_scenes(self._write_draft(Path(tmp)))
        self.assertEqual(len(scenes), 2)
        self.assertEqual(scenes[0]["visual_hint"], "1919년 홍릉, 상복의 황제")
        self.assertEqual(scenes[0]["card_text"], "1919년 홍릉")  # 쉼표 앞 절만
        self.assertNotIn("일반 주석", scenes[1]["text"])
        self.assertIn("이어지는 문장.", scenes[1]["text"])
        self.assertEqual(scenes[0]["visual"]["type"], "card")
        # 기본 모션 줌인/줌아웃 교차
        self.assertEqual(scenes[0]["visual"]["motion"], "zoom-in")
        self.assertEqual(scenes[1]["visual"]["motion"], "zoom-out")

    def test_merge_preserves_manual_edits_when_text_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft = self._write_draft(Path(tmp))
            scenes = produce_video.parse_scenes(draft)
            scenes[0]["visual"] = {"type": "ai-image", "file": "genai/scene-01.png",
                                   "prompt": "test", "motion": "pan-left"}
            scenes[0]["card_text"] = "수동 문구"
            scenes_path = Path(tmp) / "scenes.json"
            scenes_path.write_text(json.dumps({"scenes": scenes}, ensure_ascii=False), encoding="utf-8")

            merged = produce_video.load_or_merge_scenes(draft, scenes_path)
            self.assertEqual(merged[0]["visual"]["type"], "ai-image")
            self.assertEqual(merged[0]["visual"]["motion"], "pan-left")
            self.assertEqual(merged[0]["card_text"], "수동 문구")

            # 본문이 바뀐 씬은 수동 필드를 승계하지 않는다 (안전 우선)
            draft.write_text(self.DRAFT.replace("첫 씬 본문입니다.", "바뀐 본문입니다."), encoding="utf-8")
            merged2 = produce_video.load_or_merge_scenes(draft, scenes_path)
            self.assertEqual(merged2[0]["visual"]["type"], "card")

    def test_legacy_image_field_migrates_to_visual(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft = self._write_draft(Path(tmp))
            scenes = produce_video.parse_scenes(draft)
            old = [dict(s) for s in scenes]
            old[0].pop("visual")
            old[0]["image"] = "assets/photo.png"  # 구버전 스키마
            scenes_path = Path(tmp) / "scenes.json"
            scenes_path.write_text(json.dumps({"scenes": old}, ensure_ascii=False), encoding="utf-8")
            merged = produce_video.load_or_merge_scenes(draft, scenes_path)
            self.assertEqual(merged[0]["visual"]["type"], "file")
            self.assertEqual(merged[0]["visual"]["file"], "assets/photo.png")

    def test_split_sentences_and_proportional_cues(self):
        cues = produce_video._cues_proportional(
            produce_video.split_sentences("첫 문장입니다. 두 번째는 조금 더 깁니다! 끝?"), 10.0)
        self.assertEqual(len(cues), 3)
        self.assertAlmostEqual(cues[0]["start"], 0.0)
        self.assertAlmostEqual(cues[-1]["end"], 10.0, places=2)
        self.assertLess(cues[0]["end"] - cues[0]["start"],
                        cues[1]["end"] - cues[1]["start"])  # 글자수 비례

    def test_kenburns_expr(self):
        self.assertIn("zoompan=z='1+0.10*on/240'", produce_video.kenburns_expr("zoom-in", 240))
        self.assertIn("1.10-0.10*on/240", produce_video.kenburns_expr("zoom-out", 240))
        self.assertIn("(1-on/240)", produce_video.kenburns_expr("pan-left", 240))
        self.assertIn("1.001", produce_video.kenburns_expr("none", 240))


class TestUploadYoutube(unittest.TestCase):
    def _make_render_dir(self, base: Path, slug: str, meta: dict | None, with_video=True) -> Path:
        d = base / slug
        d.mkdir(parents=True)
        if with_video:
            (d / "final.mp4").write_bytes(b"\x00")
        if meta is not None:
            (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return d

    def test_load_meta_validates_required_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self._make_render_dir(Path(tmp), "ok", {"title_final": "제목", "description": "설명"})
            video, meta = upload_youtube.load_meta(d)
            self.assertTrue(video.exists())
            self.assertEqual(meta["title_final"], "제목")

            bad = self._make_render_dir(Path(tmp), "no-title", {"description": "설명"})
            with self.assertRaises(ValueError):
                upload_youtube.load_meta(bad)

            no_meta = self._make_render_dir(Path(tmp), "no-meta", None)
            with self.assertRaises(FileNotFoundError):
                upload_youtube.load_meta(no_meta)

    def test_find_pending_skips_published_and_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            meta = {"title_final": "t", "description": "d"}
            ready = self._make_render_dir(base, "ready", meta)
            done = self._make_render_dir(base, "done", meta)
            self._make_render_dir(base, "no-video", meta, with_video=False)
            published = [{"render_dir": str(done)}]
            pending = upload_youtube.find_pending(base, published)
            self.assertEqual(pending, [ready])

    def test_find_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.assertIsNone(upload_youtube.find_thumbnail(d))
            (d / "thumbnail.jpg").write_bytes(b"\x00")
            self.assertEqual(upload_youtube.find_thumbnail(d).name, "thumbnail.jpg")
            (d / "thumbnail.png").write_bytes(b"\x00")  # png 우선
            self.assertEqual(upload_youtube.find_thumbnail(d).name, "thumbnail.png")


if __name__ == "__main__":
    unittest.main()
