"""Mọi prompt bám Dòng nhạc (music_line) + Thể loại (music_style) đã chọn."""
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from backend.cover.music_line import line_key, line_profile, lyrics_language
from backend.cover.style_prompt import generate_cover_styles, style_signature
from backend.cover.suno_cover import cover_styles_for_project
from backend.video import cover_scene, thumbnail_ai

VI_LYRICS = ("Sao mình chưa nắm tay nhau, để bao năm tháng trôi qua thật mau. "
             "Người ơi có biết em vẫn đợi chờ dưới ánh trăng")
EN_LYRICS = ("I keep on waiting for the night to fall, and every time I hear you "
             "call my name I come running back to you")


class _Config:
    api_key = "test-key"
    model = "gpt-4.1"

    @staticmethod
    def to_client_kwargs():
        return {"api_key": "test-key"}


def _client(text: str):
    response = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=text))])
    create = mock.MagicMock(return_value=response)
    return SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=create))), create


class LineProfileTests(unittest.TestCase):
    def test_keys(self):
        self.assertEqual("us-uk", line_key("US-UK"))
        self.assertEqual("vn", line_key("VN"))
        self.assertEqual("korean", line_key("Korean"))
        self.assertEqual("", line_key(""))
        self.assertEqual("custom", line_key("Latin"))
        self.assertEqual("Latin", line_profile("Latin")["label"])

    def test_lyrics_language_comes_from_the_lyrics(self):
        self.assertEqual("Vietnamese", lyrics_language(VI_LYRICS, "US-UK"))
        self.assertEqual("English", lyrics_language(EN_LYRICS, "VN"))
        self.assertEqual("Korean", lyrics_language("사랑해요 " * 10, ""))
        self.assertEqual("English", lyrics_language("", "US-UK"))   # chưa có lời


class SunoStylesFollowSelectionTests(unittest.TestCase):
    def test_us_uk_deep_house_is_not_vietnamese_ballad(self):
        styles = cover_styles_for_project("Deep House", "Cảnh núi rừng, ballad buồn",
                                          "ballad", "female", "US-UK", "English")
        self.assertTrue(styles.startswith("Deep House, "))
        low = styles.casefold()
        self.assertNotIn("vietnamese", low)
        self.assertNotIn("ballad", low)
        self.assertNotIn("latin", low)
        self.assertIn("sung in English", styles)

    def test_us_uk_line_with_vietnamese_lyrics_sings_vietnamese(self):
        styles = cover_styles_for_project("Ballad", music_line="US-UK",
                                          lyrics_lang="Vietnamese")
        self.assertTrue(styles.startswith("Ballad, "))
        self.assertIn("sung in Vietnamese", styles)

    def test_each_genre_and_line_gets_its_own_sound(self):
        for genre, word in (("Future House", "Future House"),
                            ("Tropical House", "Tropical House"),
                            ("Mix Việt", "Vietmix"), ("Lofi", "Lo-fi"),
                            ("Rock", "Rock"), ("R&B", "R&B")):
            self.assertIn(word, cover_styles_for_project(genre, music_line="Korean"))
        self.assertNotIn("K-pop", cover_styles_for_project("Pop", music_line="Korean"))
        self.assertTrue(cover_styles_for_project("Pop").startswith("Pop, "))

    def test_signature_changes_with_line_and_lyrics_language(self):
        base = style_signature("Ballad", "", "", "female")
        self.assertNotEqual(base, style_signature("Ballad", "", "", "female", "", "US-UK"))
        self.assertNotEqual(base, style_signature("Ballad", "", "", "female", "", "",
                                                  "English"))

    def test_ai_receives_line_genre_and_rules(self):
        raw = ("Western US-UK deep house cover, 122 BPM, smooth four-on-the-floor groove, "
               "warm sub bass, airy pads, plucked synth hooks, spacious chorus, clean mix")
        client, create = _client(json.dumps({"styles": raw}))
        with mock.patch("openai.OpenAI", return_value=client):
            styles, source = generate_cover_styles(
                "Deep House", "Cảnh núi rừng", "ballad", "female",
                music_line="US-UK", lyrics_lang="English", api_config=_Config())
        self.assertEqual("ai", source)
        self.assertIn("sung in English", styles)
        system = create.call_args.kwargs["messages"][0]["content"]
        user = create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("genre_SELECTED_BY_USER", system)
        self.assertIn("Never add Latin", system)
        self.assertIn('"genre_SELECTED_BY_USER": "Deep House"', user)
        self.assertIn("US-UK — market modifier only", user)
        self.assertIn('"canonical_genre_profile_MUST_FOLLOW"', user)
        self.assertIn('"lyrics_language": "English"', user)

    def test_ai_adding_unselected_genre_or_region_falls_back(self):
        for raw in (
            "Latin deep house cover, 122 BPM, reggaeton-tinged drums, warm sub bass, "
            "airy pads, plucked synth hooks, spacious chorus, clean modern club mix",
            "Vietnamese emotional ballad, 70 BPM, warm piano, soft strings, gentle "
            "acoustic guitar, restrained drums, dynamic heartfelt chorus, intimate mix",
        ):
            client, _ = _client(json.dumps({"styles": raw}))
            with mock.patch("openai.OpenAI", return_value=client):
                styles, source = generate_cover_styles(
                    "Deep House", music_line="US-UK", lyrics_lang="English",
                    api_config=_Config())
            self.assertTrue(source.startswith("fallback:"), raw)
            self.assertTrue(styles.startswith("Deep House, "))
            self.assertIn("sung in English", styles)

    def test_music_line_cannot_inject_second_genre(self):
        raw = ("Korean K-pop ballad cover, 72 BPM, warm piano, lush strings, soft "
               "acoustic guitar, restrained drums, emotional dynamic chorus, polished mix")
        client, _ = _client(json.dumps({"styles": raw}))
        with mock.patch("openai.OpenAI", return_value=client):
            _styles, source = generate_cover_styles(
                "Ballad", music_line="Korean", lyrics_lang="Korean", api_config=_Config())
        self.assertTrue(source.startswith("fallback:"))
        self.assertNotIn("K-pop", _styles)
        self.assertTrue(_styles.startswith("Ballad, "))


class ImagePromptsFollowLineTests(unittest.TestCase):
    def test_template_cover_uses_line_and_genre(self):
        us = cover_scene.template_scene({"title": "Sao Mình Chưa Nắm Tay Nhau",
                                         "purpose": "Deep House", "music_line": "US-UK",
                                         "description": "Cảnh núi rừng"})
        self.assertNotIn("Vietnamese", us["thumbnail"])
        self.assertIn("US-UK Deep House music playlist", us["thumbnail"])
        self.assertIn("DJ", us["thumbnail"])            # Deep House → remix look
        self.assertIn("forest", us["scene"])            # ý tưởng «núi rừng»
        vn = cover_scene.template_scene({"title": "x", "purpose": "Ballad",
                                         "music_line": "VN"})
        self.assertIn("young Vietnamese woman", vn["thumbnail"])
        self.assertIn("Vietnamese Ballad music playlist", vn["thumbnail"])

    def test_ai_scene_prompt_carries_selection(self):
        good = {"scene": "a misty pine forest valley at dusk with soft light",
                "thumbnail": "A fictional young woman DJ with a black face mask, "
                             "neon forest valley behind her, cinematic photo",
                "intro": "Bring the reference image to life with a very slow push-in",
                "loop": "Same place, still camera, mist drifting gently, seamless loop"}
        client, create = _client(json.dumps(good))
        with mock.patch("openai.OpenAI", return_value=client):
            out = cover_scene.ai_scene({"title": "x", "purpose": "Deep House",
                                        "music_line": "US-UK"}, "photoreal",
                                       "character_pet", "", _Config())
        self.assertIsNotNone(out)
        system = create.call_args.kwargs["messages"][0]["content"]
        user = create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("US-UK English music playlist", system)
        self.assertNotIn("Vietnamese mixtape", system)
        self.assertIn("music genre: Deep House; music line: US-UK", user)
        self.assertNotIn("young Vietnamese", user)

    def test_mixtape_thumbnail_follows_line(self):
        us = thumbnail_ai.build_prompt("Sao Minh", "Deep House", {
            "mixtape": True, "music_line": "US-UK"})
        self.assertNotIn("Vietnamese", us)
        self.assertIn("US-UK music mixtape", us)
        vn = thumbnail_ai.build_prompt("Sao Mình", "Ballad", {"mixtape": True,
                                                             "music_line": "VN"})
        self.assertIn("Vietnamese music mixtape", vn)


class ManifestSignatureTests(unittest.TestCase):
    def test_old_manifest_without_line_still_matches(self):
        from backend.video import prompt_workflow
        inputs = {"context": {"title": "a", "music_line": "VN"}, "style": "real"}
        legacy = prompt_workflow._legacy_signature(inputs)
        old = {"context": {"title": "a"}, "style": "real"}
        self.assertEqual(prompt_workflow.prompt_catalog.prompt_hash(
            json.dumps(old, ensure_ascii=False, sort_keys=True)), legacy)
        self.assertIsNone(prompt_workflow._legacy_signature(old))


class CoupleCastTests(unittest.TestCase):
    CTX = {"title": "Sao Mình Chưa Nắm Tay Nhau", "purpose": "Ballad", "music_line": "VN",
           "description": "Cảnh núi rừng, 1 cặp đôi yêu nhau nhưng ngại ngùng không "
                          "dám nắm tay nhau"}

    def test_detects_couple_from_description(self):
        self.assertTrue(cover_scene.wants_couple(self.CTX))
        self.assertTrue(cover_scene.wants_couple({"visual_idea": "two lovers on a beach"}))
        self.assertFalse(cover_scene.wants_couple({"description": "Cảnh núi rừng, buồn"}))
        self.assertFalse(cover_scene.wants_couple({"description": "nhớ người yêu cũ"}))

    def test_couple_description_draws_a_couple_everywhere(self):
        prompts, motions, cont = cover_scene.build(self.CTX, "photoreal", "character_pet",
                                                   use_ai=False)
        self.assertEqual("couple", cont["cast"])
        self.assertIn("Vietnamese couple", prompts["0"])
        self.assertIn("veil", prompts["0"])
        self.assertIn("forest", prompts["0"])
        self.assertIn("the couple", prompts["1"])
        self.assertIn("behind the couple", prompts["2"])
        self.assertIn("keep the couple", motions["0"])
        for k in ("2", "3", "4", "5"):
            self.assertIn("same couple", motions[k])
            self.assertNotIn("the woman (her", motions[k])

    def test_no_couple_keeps_single_masked_woman(self):
        ctx = {**self.CTX, "description": "Cảnh núi rừng"}
        prompts, motions, cont = cover_scene.build(ctx, "photoreal", "character_pet",
                                                   use_ai=False)
        self.assertNotIn("cast", cont)
        self.assertIn("woman", prompts["0"])
        self.assertNotIn("couple", prompts["0"])
        self.assertIn("same woman", motions["2"])
        # Viết lại chuyển động cho hồ sơ cũ (ảnh 1 cô gái) → giữ 1 cô gái.
        _, old, _ = cover_scene.build(self.CTX, "photoreal", "character_pet",
                                      use_ai=False, couple=False)
        self.assertIn("same woman", old["2"])

    def test_scenery_never_gets_people(self):
        prompts, _, cont = cover_scene.build(self.CTX, "photoreal", "scenery",
                                             use_ai=False)
        self.assertNotIn("cast", cont)
        self.assertIn("No people", prompts["0"])

    def test_ai_scene_asks_for_couple_and_validates(self):
        good = {"scene": "a misty mountain forest path in the evening light",
                "thumbnail": "A shy fictional young Vietnamese couple, her lace veil and "
                             "his black face mask, misty forest behind them, cinematic",
                "intro": "Bring the reference image to life with a very slow push-in",
                "loop": "Same place, still camera, mist drifting gently, seamless loop"}
        client, create = _client(json.dumps(good))
        with mock.patch("openai.OpenAI", return_value=client):
            out = cover_scene.ai_scene(self.CTX, "photoreal", "character_pet", "",
                                       _Config(), couple=True)
        self.assertIsNotNone(out)
        user = create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("COUPLE", user)
        self.assertNotIn("never a couple", user)
        single = {**good, "thumbnail": "A fictional young woman with a lace veil in a "
                                       "misty forest, cinematic photo"}
        client, _ = _client(json.dumps(single))
        with mock.patch("openai.OpenAI", return_value=client):
            self.assertIsNone(cover_scene.ai_scene(self.CTX, "photoreal", "character_pet",
                                                   "", _Config(), couple=True))


if __name__ == "__main__":
    unittest.main()
