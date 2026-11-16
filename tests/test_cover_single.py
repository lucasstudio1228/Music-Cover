"""Tool Cover (2026-10-29): ảnh bìa (nữ che mặt) → bảng nhân vật + bảng bối cảnh
vẽ TỪ ảnh bìa → clip 00 intro, 01 loop, 02–05 bốn góc quay; sóng âm; mixset;
migration M030/M031.

Không gọi AI/trình duyệt thật — AI viết prompt luôn bị thay bằng mock."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.video import config, cover_scene, prompt_catalog as catalog  # noqa: E402
from backend.video import prompt_workflow as workflow  # noqa: E402
from backend.video.translate import non_english_fields  # noqa: E402

_PATCHES = []
_TMP = None


def setUpModule():
    global _TMP
    from backend.video import thumbnail_ai, thumbnail_recipe
    _TMP = tempfile.TemporaryDirectory()
    _PATCHES.extend([
        patch.object(thumbnail_recipe, "LEDGER", Path(_TMP.name) / "thumbnail_recipes.json"),
        patch.object(thumbnail_ai, "load_settings",
                     lambda *a, **k: thumbnail_ai.ThumbAISettings(engine="pil")),
        # Chế độ mặc định của tool Cover — giữ cố định dù test khác có đổi.
        patch.object(config, "PARAMS", config.VideoParams(
            image_count=3, scene_clips=6, rest_clips=5, min_total_clips=6, cover=True)),
    ])
    for p in _PATCHES:
        p.start()


def tearDownModule():
    for p in reversed(_PATCHES):
        p.stop()
    _TMP.cleanup()


AUTUMN = {"title": "Vietmix Deep Chill mùa thu", "visual_idea": "", "music_idea": "",
          "purpose": "Deep House", "description": "", "instrument": ""}


class TemplateSceneTests(unittest.TestCase):
    def test_season_word_does_not_match_rain(self):
        s = cover_scene.template_scene(AUTUMN)
        self.assertIn("autumn", s["scene"])
        self.assertNotIn("raindrops", s["scene"])

    def test_keywords_pick_place_and_time(self):
        s = cover_scene.template_scene({"title": "Ballad đêm mưa", "purpose": "Ballad"})
        self.assertIn("rain", s["scene"])
        self.assertIn("night", s["scene"])
        self.assertIn("beach", cover_scene.template_scene({"title": "Lofi biển xanh"})["scene"])

    def test_prompts_are_english_distinct_and_textless(self):
        for cast in ("character_pet", "scenery"):
            s = cover_scene.template_scene(AUTUMN, cast)
            fields = {k: s[k] for k in ("thumbnail", "intro", "loop")}
            self.assertFalse(non_english_fields(fields))
            self.assertEqual(len(set(fields.values())), 3)
            self.assertIn("no text", s["thumbnail"].lower().replace("absolutely no text", "no text"))
            self.assertIn("loops seamlessly", s["loop"])
        self.assertIn("No people", cover_scene.template_scene(AUTUMN, "scenery")["thumbnail"])

    def test_character_sheet_prompt_differs_per_scene(self):
        """LIVE 2026-11-09: prompt bảng nhân vật là câu mẫu cố định → trùng #19."""
        for kw in ({}, {"couple": True}, {"male": True}):
            a = cover_scene.sheet_prompts("a rainy tram stop at dusk", "character", **kw)["1"]
            b = cover_scene.sheet_prompts("a lantern-lit river pier", "character", **kw)["1"]
            self.assertNotEqual(a, b)
            self.assertIn("a rainy tram stop at dusk", a)

    def test_build_shapes_and_directive(self):
        prompts, motions, cont = cover_scene.build(AUTUMN, "brief", "character_pet",
                                                   "Title space on the left.", use_ai=False)
        self.assertEqual(sorted(prompts), ["0", "1", "2"])
        self.assertEqual(sorted(motions), ["0", "1", "2", "3", "4", "5"])
        self.assertTrue(prompts["0"].endswith("Title space on the left."))
        self.assertEqual(cont["source"], "template")
        self.assertIn("CHARACTER REFERENCE SHEET", prompts["1"])
        self.assertIn("attached reference image", prompts["1"])
        self.assertIn("SCENE REFERENCE SHEET", prompts["2"])
        self.assertIn("NO people", prompts["2"])
        angles = [motions[k] for k in ("2", "3", "4", "5")]
        self.assertEqual(len(set(angles)), 4)
        for a in angles:
            self.assertIn("design sheets", a)
            self.assertIn("covered", a)
        self.assertFalse(non_english_fields({**prompts, **motions}))

    def test_scenery_build_has_two_place_sheets_and_no_people(self):
        prompts, motions, _ = cover_scene.build(AUTUMN, "b", "scenery", use_ai=False)
        for k in ("1", "2"):
            self.assertTrue(config.is_scenery_prompt(prompts[k]))
            self.assertIn("NO people", prompts[k])
        for k in ("2", "3", "4", "5"):
            self.assertIn("no people", motions[k])

    def test_ai_scene_without_key_or_with_bad_reply_falls_back(self):
        self.assertIsNone(cover_scene.ai_scene(AUTUMN, "b", "scenery", "", None))
        cfg = SimpleNamespace(api_key="k", model="gpt-test", to_client_kwargs=lambda: {})
        bad = Mock()
        bad.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"scene": "x"}'))])
        logs = []
        with patch("openai.OpenAI", return_value=bad):
            self.assertIsNone(cover_scene.ai_scene(AUTUMN, "b", "scenery", "", cfg, logs.append))
        self.assertTrue(logs)

    def test_ai_scene_valid_reply_is_used(self):
        cfg = SimpleNamespace(api_key="k", model="gpt-test", to_client_kwargs=lambda: {})
        data = {"scene": "A rooftop terrace above a city at dusk in autumn.",
                "thumbnail": "Cinematic still of a fictional young woman in a black face "
                             "mask on a rooftop terrace at dusk, no text at all.",
                "intro": "Bring the image to life with one very slow push-in, no cuts.",
                "loop": "Same rooftop, still camera, gentle string lights swaying, seamless loop."}
        ok = Mock()
        ok.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(data)))])
        with patch("openai.OpenAI", return_value=ok):
            prompts, motions, cont = cover_scene.build(AUTUMN, "b", "character_pet", api_config=cfg)
        self.assertEqual(cont["source"], "ai")
        self.assertEqual(prompts["0"], data["thumbnail"])
        self.assertEqual({k: motions[k] for k in ("0", "1")},
                         {"0": data["intro"], "1": data["loop"]})

    def test_ai_scene_with_man_or_bare_face_is_rejected(self):
        cfg = SimpleNamespace(api_key="k", model="gpt-test", to_client_kwargs=lambda: {})
        base = {"scene": "A rooftop terrace above a city at dusk in autumn.",
                "intro": "Bring the image to life with one very slow push-in, no cuts.",
                "loop": "Same rooftop, still camera, gentle string lights swaying, seamless loop."}
        for thumb in ("Cinematic still of a young man DJ on a rooftop at dusk, no text.",
                      "Cinematic still of a young woman smiling on a rooftop at dusk, no text.",
                      "A masked woman and a man as a couple on a rooftop at dusk, no text."):
            bad = Mock()
            bad.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps({**base, "thumbnail": thumb})))])
            with patch("openai.OpenAI", return_value=bad):
                self.assertIsNone(cover_scene.ai_scene(AUTUMN, "b", "character_pet", "", cfg),
                                  thumb)


class SingleConfigTests(unittest.TestCase):
    def test_single_mode_plan_and_refs(self):
        self.assertTrue(config.single_image())
        self.assertFalse(config.single_image(config.VideoParams()))
        self.assertEqual(config.PARAMS.total_clips, 6)
        self.assertEqual(config.generate_ingredient_plan(6),
                         [[0], [1, 2], [1, 2], [1, 2], [1, 2], [1, 2]])
        self.assertEqual(config.image_order(), (0, 1, 2))
        self.assertEqual(config.image_refs(0), ())
        self.assertEqual(config.image_refs(1), (0,))
        self.assertEqual(config.image_refs(2), (0,))
        self.assertEqual(sorted(config.image_roles("character_pet")), [0, 1, 2])
        self.assertIn("vẽ từ ảnh bìa", config.image_roles("character_pet")[1])
        self.assertEqual(config.thumbnail_refs(), ())
        self.assertEqual(config.thumbnail_ref_note("a cover"), "")
        self.assertEqual(config.intro_motion_prompt("scenery"), config.INTRO_MOTION_PROMPT_SINGLE)


class SinglePrepareTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="cover-single-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for p in (patch.object(config, "MEDIA_ROOT", root / "media"),
                  patch.object(catalog, "CATALOG_PATH", root / "catalog.sqlite3"),
                  patch.object(catalog, "APP_DB_PATH", root / "absent.sqlite3"),
                  patch.object(catalog, "bootstrap_existing", return_value={}),
                  patch.object(workflow, "project_context", return_value=dict(AUTUMN)),
                  patch("backend.core_bridge.get_api_config_from_db",
                        return_value=SimpleNamespace(api_key="test")),
                  patch.object(cover_scene, "ai_scene", return_value=None)):
            p.start()
            self.addCleanup(p.stop)

    def test_prepare_writes_cover_two_sheets_and_six_motions_then_resumes(self):
        with patch("backend.video.prompt_gen.generate_prompts") as legacy:
            first = workflow.prepare(7, "Deep Chill")
            second = workflow.prepare(7, "Deep Chill")
        legacy.assert_not_called()
        self.assertEqual(first, second)
        self.assertTrue(first["single_image"])
        self.assertEqual(first["workflow_version"], workflow.SINGLE_WORKFLOW_VERSION)
        self.assertEqual(sorted(first["prompts"]), ["0", "1", "2"])
        self.assertEqual(sorted(first["motions"]), ["0", "1", "2", "3", "4", "5"])
        self.assertIn("autumn", first["continuity"]["scene"])

    def test_v3_manifest_upgrades_and_keeps_cover_intro_loop(self):
        first = workflow.prepare(11, "Deep Chill")
        v3 = {**first, "workflow_version": workflow.COVER_V3,
              "prompts": {"0": "Old masked woman cover, no text."},
              "motions": {"0": "Old intro push-in, no cuts at all.",
                          "1": "Old loop, still camera, loops seamlessly."}}
        v3.pop("prompt_hashes", None)
        workflow.save_manifest(config.images_dir(11, "Deep Chill") / "prompts.json", v3)
        got = workflow.prepare(11, "Deep Chill")
        self.assertEqual(got["workflow_version"], workflow.SINGLE_WORKFLOW_VERSION)
        self.assertEqual(got["upgraded_from_workflow_version"], workflow.COVER_V3)
        self.assertEqual(got["prompts"]["0"], v3["prompts"]["0"])
        self.assertEqual(got["motions"]["0"], v3["motions"]["0"])
        self.assertEqual(got["motions"]["1"], v3["motions"]["1"])
        self.assertEqual(sorted(got["prompts"]), ["0", "1", "2"])
        self.assertEqual(sorted(got["motions"]), ["0", "1", "2", "3", "4", "5"])
        # Không phải v3 → giữ nguyên
        self.assertIs(workflow.upgrade_cover_manifest(11, got), got)

    def test_restart_rewrites_old_cover_template_but_resume_keeps_it(self):
        first = workflow.prepare(9, "Deep Chill")
        self.assertEqual(first["cover_rev"], cover_scene.COVER_REV)
        old = {**first, "cover_rev": None, "prompts": {**first["prompts"], "0": "Old cover seen from behind, no text."}}
        workflow.save_manifest(config.images_dir(9, "Deep Chill") / "prompts.json", old)
        kept = workflow.prepare(9, "Deep Chill")
        self.assertEqual(kept["prompts"]["0"], old["prompts"]["0"])
        fresh = workflow.prepare(9, "Deep Chill", allow_rebuild=True)
        self.assertIn("into the camera", fresh["prompts"]["0"])
        self.assertEqual(fresh["cover_rev"], cover_scene.COVER_REV)

    def test_clip_prompt_list_uses_thumbnail_only_for_intro(self):
        from backend.video import flow_driver
        saved = workflow.prepare(8, "Deep Chill")
        clips = flow_driver.clip_prompt_list(8, "Deep Chill")
        self.assertEqual(len(clips), 6)
        self.assertEqual(clips[0]["ingredients"], [config.IMG_THUMBNAIL])
        for c in clips[1:]:
            self.assertEqual(c["ingredients"], [1, 2])
        self.assertIn("push-in", json.dumps(clips[0], ensure_ascii=False))
        self.assertIn("loops seamlessly", json.dumps(clips[1], ensure_ascii=False))
        self.assertNotEqual(saved["motions"]["0"], saved["motions"]["1"])

    def test_cover_fallback_motion_by_clip(self):
        from backend.video import flow_driver
        self.assertEqual(flow_driver.cover_fallback_motion(0, "character_pet"),
                         config.intro_motion_prompt("character_pet"))
        self.assertEqual(flow_driver.cover_fallback_motion(1, "character_pet"),
                         config.LOOP_MOTION_PROMPT_SINGLE)
        side = flow_driver.cover_fallback_motion(3, "character_pet")
        self.assertIn("side tracking", side)
        self.assertNotEqual(side, flow_driver.cover_fallback_motion(4, "character_pet"))


class WaveformTests(unittest.TestCase):
    def test_wave_filter_graph(self):
        from backend.cover.overlay import wave_filter
        g = wave_filter(1920, 1080, 8.0)
        self.assertIn("showfreqs=s=64x", g)
        self.assertIn("enable='gte(t,8.00)'", g)
        self.assertTrue(g.endswith("[wv]"))

    def test_playlist_overlay_only_shows_current_title_without_artist(self):
        """Sau intro chỉ hiện tên bài hiện tại ở góc, tuyệt đối không hiện ca sĩ."""
        from backend.cover.overlay import build_ass
        artist = "Quốc Thiên, Đình Dũng (Remix Version)"
        info = {"tracks": [
            {"name": "Kẻ Say Tình 2", "song_id": 1, "start_seconds": 0, "end_seconds": 100},
            {"name": "Hơn Cả Yêu", "song_id": 2, "start_seconds": 100, "end_seconds": 200}]}
        songs = {1: {"title": "Kẻ Say Tình 2", "artist": artist, "lines": []},
                 2: {"title": "Hơn Cả Yêu", "artist": "Đức Phúc", "lines": []}}
        ass = build_ass(info, songs, {"language": "vi", "show_tracklist": True,
                                      "show_lyrics": False,
                                      "channel_name": "Lucas Studio"}, 200, 8)
        rows = [l for l in ass.splitlines() if l.startswith("Dialogue")]
        titles = [l for l in rows if ",NowTitle," in l]
        self.assertEqual(2, len(titles))
        self.assertTrue(any(l.endswith("}Kẻ Say Tình 2") for l in titles))
        self.assertTrue(any(l.endswith("}Hơn Cả Yêu") for l in titles))
        self.assertFalse(any(artist in l or "Đức Phúc" in l for l in rows))
        watermark = [l for l in rows if ",Channel," in l]
        self.assertEqual(1, len(watermark))
        self.assertIn(r"\an9\pos(", watermark[0])
        self.assertTrue(watermark[0].endswith("Lucas Studio"))

    def test_lyrics_show_only_current_line_in_color(self):
        """Lyrics: chỉ câu đang hát (không câu trước/kế), chữ gradient nhiều màu."""
        import re
        from backend.cover.overlay import build_ass
        info = {"tracks": [
            {"name": "A", "song_id": 1, "start_seconds": 0, "end_seconds": 60},
            {"name": "B", "song_id": 2, "start_seconds": 60, "end_seconds": 120}]}
        songs = {1: {"title": "A", "artist": "", "lines": [
                     {"text": "Hà Nội mùa thu", "start": 10, "end": 13},
                     {"text": "Cây cơm nguội vàng", "start": 14, "end": 17}]},
                 2: {"title": "B", "artist": "", "lines": [
                     {"text": "Lá vàng rơi", "start": 5, "end": 8}]}}
        ass = build_ass(info, songs, {"language": "vi", "channel_name": "X"}, 120, 2)
        rows = [l for l in ass.splitlines() if l.startswith("Dialogue")]
        self.assertFalse(any(",LyDim," in l for l in rows))
        cur = [l for l in rows if ",LyCur," in l]
        self.assertEqual(3, len(cur))                       # 1 dòng mỗi câu
        plain = [re.sub(r"\{[^}]*\}", "", l.split(",,", 1)[1].split(",", 4)[-1]) for l in cur]
        self.assertEqual(["Hà Nội mùa thu", "Cây cơm nguội vàng", "Lá vàng rơi"], plain)
        # Mỗi câu hiện một mình: các khoảng thời gian không chồng nhau.
        times = [l.split(",")[1:3] for l in cur]
        self.assertEqual(["0:00:10.00", "0:00:14.00"], times[0])
        self.assertLessEqual(times[0][1], times[1][0])
        # Nhiều màu: mỗi câu có nhiều mã màu khác nhau; bài 2 khác bảng màu bài 1.
        colors = [set(re.findall(r"\\1c(&H[0-9A-F]{6}&)", l)) for l in cur]
        self.assertTrue(all(len(c) >= 3 for c in colors))
        self.assertNotEqual(re.findall(r"\\1c(&H[0-9A-F]{6}&)", cur[0])[0],
                            re.findall(r"\\1c(&H[0-9A-F]{6}&)", cur[2])[0])
        self.assertEqual(3, len([l for l in rows if ",LyGlow," in l]))


class CoverPersonTests(unittest.TestCase):
    """Ảnh bìa kiểu mixtape: cô gái trẻ hư cấu, mặc gợi cảm, che mặt, nhìn thẳng camera."""

    def test_person_faces_camera_by_genre(self):
        remix = cover_scene.template_scene(AUTUMN)["thumbnail"]
        self.assertIn("DJ", remix)
        self.assertIn("into the camera", remix)
        self.assertIn("fictional", remix)
        self.assertNotIn("from behind", remix)
        ballad = cover_scene.template_scene({"title": "Ballad đêm mưa", "purpose": "Ballad"})
        self.assertIn("young Vietnamese woman", ballad["thumbnail"])
        self.assertIn("same face", ballad["intro"])
        for ctx in (AUTUMN, {"title": "Cặp đôi mùa thu", "purpose": "Ballad"},
                    {"title": "Acoustic chill", "purpose": "Acoustic guitar"},
                    {"title": "Nhạc gốc", "purpose": "Pop"}):
            thumb = cover_scene.template_scene(ctx)["thumbnail"]
            self.assertTrue(cover_scene._woman_masked(thumb), thumb)
            self.assertIn("fully clothed", thumb)
            self.assertNotIn("couple", thumb)

    def test_scenery_still_has_no_people(self):
        s = cover_scene.template_scene(AUTUMN, "scenery")
        self.assertIn("No people", s["thumbnail"])
        # Đúng genre vẫn được có DJ booth/controller; chỉ không được có DJ/người.
        self.assertNotIn("female DJ", s["thumbnail"])

    def test_vocal_cast_drives_character_and_reference_sheet(self):
        female_prompts, _, female = cover_scene.build(
            {**AUTUMN, "vocal_cast": "female"}, "brief", "character_pet",
            use_ai=False)
        male_prompts, _, male = cover_scene.build(
            {**AUTUMN, "vocal_cast": "male"}, "brief", "character_pet",
            use_ai=False)
        duet_prompts, _, duet = cover_scene.build(
            {**AUTUMN, "vocal_cast": "duet"}, "brief", "character_pet",
            use_ai=False)
        self.assertTrue(cover_scene._woman_masked(female_prompts["0"]))
        self.assertTrue(cover_scene._man_masked(male_prompts["0"]))
        self.assertTrue(cover_scene._couple_masked(duet_prompts["0"]))
        self.assertIn("of the man", male_prompts["1"])
        self.assertIn("his face", male_prompts["1"])
        self.assertNotIn("her face", male_prompts["1"])
        self.assertIn("of the couple", duet_prompts["1"])
        self.assertEqual("female", female["vocal_cast"])
        self.assertEqual("male", male["vocal_cast"])
        self.assertEqual("duet", duet["vocal_cast"])

    def test_explicit_solo_vocal_is_not_changed_to_couple_by_story(self):
        romantic = {**AUTUMN, "description": "Một cặp đôi đang yêu nhau"}
        female, _, female_cont = cover_scene.build(
            {**romantic, "vocal_cast": "female"}, "brief", "character_pet",
            use_ai=False)
        male, _, male_cont = cover_scene.build(
            {**romantic, "vocal_cast": "male"}, "brief", "character_pet",
            use_ai=False)
        auto, _, auto_cont = cover_scene.build(
            {**romantic, "vocal_cast": "auto"}, "brief", "character_pet",
            use_ai=False)
        self.assertTrue(cover_scene._woman_masked(female["0"]))
        self.assertTrue(cover_scene._man_masked(male["0"]))
        self.assertTrue(cover_scene._couple_masked(auto["0"]))
        self.assertEqual("female", female_cont["vocal_cast"])
        self.assertEqual("male", male_cont["vocal_cast"])
        self.assertEqual("duet", auto_cont["vocal_cast"])

    def test_genres_choose_distinct_authentic_scenes(self):
        jazz = cover_scene.template_scene({"title": "Đêm xanh", "purpose": "Jazz Blues"})
        rock = cover_scene.template_scene({"title": "Bùng cháy", "purpose": "Rock"})
        lofi = cover_scene.template_scene({"title": "Bình yên", "purpose": "Lofi"})
        self.assertIn("jazz lounge", jazz["scene"])
        self.assertIn("industrial warehouse", rock["scene"])
        self.assertIn("bedroom studio", lofi["scene"])
        self.assertEqual(3, len({jazz["scene"], rock["scene"], lofi["scene"]}))


class ChatGPTImageEngineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="cover-gpt-img-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        p = patch.object(config, "MEDIA_ROOT", self.root / "media")
        p.start()
        self.addCleanup(p.stop)

    @staticmethod
    def _png(w=1536, h=1024) -> bytes:
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (200, 120, 60)).save(buf, format="PNG")
        return buf.getvalue()

    def test_prompt_without_attachment_draws_from_scratch(self):
        from backend.video.chatgpt_thumbnail import chatgpt_prompt
        self.assertIn("attached", chatgpt_prompt("x"))
        fresh = chatgpt_prompt("A DJ on a rooftop.", edit=False)
        self.assertIn("from scratch", fresh)
        self.assertNotIn("attached", fresh)

    def test_draws_cover_then_sheets_from_cover_and_saves_16x9(self):
        from PIL import Image
        from backend.video.chatgpt_image import SHEET_SPEC, SPEC, generate_images_chatgpt
        calls = []

        def fake_draw(prompt, **kw):
            calls.append((prompt, kw))
            return self._png()

        prompts = {"0": "Cinematic cover photo of a masked woman DJ on a rooftop, no text.",
                   "1": "CHARACTER REFERENCE SHEET of the woman in the attached image.",
                   "2": "SCENE REFERENCE SHEET of the rooftop in the attached image."}
        out = generate_images_chatgpt(5, "Deep Chill", progress_cb=lambda m, p: None,
                                      project_name="Deep Chill", prompts_override=prompts,
                                      style="real", _draw=fake_draw)
        self.assertEqual(len(out), 3)
        self.assertEqual(len(calls), 3)
        self.assertTrue(calls[0][0].startswith(SPEC))
        self.assertIn("rooftop", calls[0][0])
        self.assertIsNone(calls[0][1].get("ref"))
        for prompt, kw in calls[1:]:
            self.assertTrue(prompt.startswith(SHEET_SPEC))
            self.assertTrue(kw["ref"].startswith(b"\xff\xd8"))   # JPEG ảnh bìa
        self.assertIn("CHARACTER", calls[1][0])
        self.assertIn("SCENE", calls[2][0])
        for f in out:
            with Image.open(f) as im:
                self.assertAlmostEqual(im.width / im.height, 16 / 9, places=2)
        # resume: đã có ảnh → không vẽ lại
        generate_images_chatgpt(5, "Deep Chill", resume=True, project_name="Deep Chill",
                                prompts_override=prompts, _draw=fake_draw)
        self.assertEqual(len(calls), 3)

    def test_sheet_without_cover_is_refused(self):
        from backend.video.chatgpt_image import generate_images_chatgpt
        with self.assertRaises(RuntimeError):
            generate_images_chatgpt(6, "x", project_name="x",
                                    prompts_override={"0": "a", "1": "b", "2": "c"},
                                    only=[1], _draw=lambda *a, **k: self._png())

    def test_reference_prompt_uses_reference_task(self):
        from backend.video.chatgpt_thumbnail import REFERENCE_TASK, chatgpt_prompt
        self.assertIn(REFERENCE_TASK, chatgpt_prompt("A sheet.", task=REFERENCE_TASK))

    def test_legacy_three_image_mode_is_refused(self):
        from backend.video.chatgpt_image import generate_images_chatgpt
        with self.assertRaises(RuntimeError):
            generate_images_chatgpt(5, "x", config.VideoParams(), project_name="x",
                                    prompts_override={"0": "a", "1": "b", "2": "c"},
                                    only=[0], _draw=lambda *a, **k: b"")

    def test_default_engine_is_chatgpt_with_muse_backup(self):
        with patch.object(config, "load_overrides", return_value={}):
            self.assertEqual(config.image_engine(), "chatgpt")
            self.assertEqual(config.image_fallback_engine(), "muse")
            self.assertEqual(config.image_engine_label(), "ChatGPT")
        with patch.object(config, "load_overrides", return_value={"image_engine": "muse"}):
            self.assertEqual(config.image_fallback_engine(), "gemini")

    def test_service_falls_back_to_muse_when_chatgpt_fails(self):
        from backend.video import chatgpt_image, muse_image, service
        msgs = []
        with patch.object(config, "load_overrides", return_value={}), \
                patch.object(chatgpt_image, "generate_images_chatgpt",
                             side_effect=RuntimeError("chưa đăng nhập ChatGPT")), \
                patch.object(muse_image, "generate_images_muse",
                             return_value=["0.png"]) as muse:
            out = service._generate_images(5, "x", lambda m, p: msgs.append(m),
                                           project_name="x", prompts_override={"0": "a"})
        self.assertEqual(out, ["0.png"])
        muse.assert_called_once()
        # Tool Cover: dự phòng chỉ vẽ ảnh còn thiếu, không xoá ảnh bìa đã có.
        self.assertTrue(muse.call_args.kwargs.get("resume"))
        self.assertTrue(any("ChatGPT" in m and "Muse.ai" in m for m in msgs))


class MixtapeThumbnailTests(unittest.TestCase):
    TRACKS = ["Em Của Ngày Hôm Qua", "Nơi Này Có Anh", "Lạc Trôi"]

    def test_mixtape_prompt_has_title_tag_and_numbered_tracklist(self):
        from backend.video.thumbnail_ai import build_prompt
        rec = {"mixtape": True, "tracklist": self.TRACKS, "layout": "left"}
        p = build_prompt("Mixtape Hoài Niệm", "Nhạc Remix Cover Cực Cuốn", rec,
                         native_wide=False)
        self.assertIn('"Mixtape Hoài Niệm"', p)
        self.assertIn("GENRE TAG", p)
        self.assertIn('"1. Em Của Ngày Hôm Qua"', p)
        self.assertIn('"3. Lạc Trôi"', p)
        self.assertIn("3D", p)
        self.assertIn("music-note", p)
        self.assertIn("person's face", p)
        plain = build_prompt("Mixtape Hoài Niệm", "Sub", {"layout": "left"})
        self.assertNotIn("TRACKLIST", plain)
        self.assertNotIn("TRACKLIST", build_prompt("T", "S", {"mixtape": True}))
        self.assertNotIn("TRACKLIST", build_prompt("T", "S", {"mixtape": True,
                                                              "tracklist": ["Một bài"]}))

    def test_cache_key_changes_with_tracklist(self):
        from backend.video.thumbnail_ai import cache_key
        cover = Path(_TMP.name) / "absent.png"
        base = cache_key("T", "S", {"layout": "left"}, "m", cover)
        a = cache_key("T", "S", {"layout": "left", "mixtape": True,
                                 "tracklist": self.TRACKS}, "m", cover)
        b = cache_key("T", "S", {"layout": "left", "mixtape": True,
                                 "tracklist": self.TRACKS[:2]}, "m", cover)
        self.assertEqual(base, cache_key("T", "S", {"layout": "left"}, "m", cover))
        self.assertEqual(len({base, a, b}), 3)

    def test_cover_tracklist_reads_songs_in_order(self):
        from backend.cover import branding
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE coversong (id INTEGER PRIMARY KEY, project_id INTEGER, "
                         "position INTEGER, title TEXT)")
            conn.executemany("INSERT INTO coversong VALUES (?, ?, ?, ?)", [
                (1, 9, 2, "Lạc Trôi"), (2, 9, 1, "Nơi Này Có Anh"), (3, 9, 3, "Lạc Trôi"),
                (4, 8, 1, "Khác"), (5, 9, 4, "Một Cái Tên Bài Hát Thật Là Dài Dòng Quá Mức")])
            conn.commit()
            conn.close()
            with patch.object(branding, "DB_PATH", db):
                got = branding.cover_tracklist(9)
                self.assertEqual(branding.cover_tracklist(9, limit=1), ["Nơi Này Có Anh"])
        self.assertEqual(got[:2], ["Nơi Này Có Anh", "Lạc Trôi"])
        self.assertEqual(len(got), 3)
        self.assertTrue(got[2].endswith("…") and len(got[2]) <= 32)


class MigrationTests(unittest.TestCase):
    def test_m030_adds_waveform_and_m031_switches_style_only_without_images(self):
        from backend import migrations
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT, video_style TEXT)")
            conn.execute("CREATE TABLE coversettings (id INTEGER PRIMARY KEY, project_id INTEGER)")
            conn.executemany("INSERT INTO project VALUES (?, ?, ?)",
                             [(1, "Empty", "2d"), (2, "Has Img", "2d"), (3, "Anime", "anime")])
            conn.commit()
            conn.close()
            media = Path(d) / "media"
            with patch.object(migrations, "DB_PATH", db), \
                    patch.object(config, "MEDIA_ROOT", media):
                img = config.images_dir(2, "Has Img")
                img.mkdir(parents=True, exist_ok=True)
                (img / "0.png").write_bytes(b"x")
                migrations.migrate_add_coversettings_show_waveform()
                migrations.migrate_default_style_real()
                migrations.migrate_default_style_real()   # chạy lại: không đổi gì thêm
            conn = sqlite3.connect(db)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(coversettings)")]
            styles = dict(conn.execute("SELECT id, video_style FROM project"))
            conn.close()
        self.assertIn("show_waveform", cols)
        self.assertEqual(styles, {1: "real", 2: "2d", 3: "anime"})


if __name__ == "__main__":
    unittest.main()
