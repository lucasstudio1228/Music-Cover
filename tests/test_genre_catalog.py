import unittest
from types import SimpleNamespace

from backend.cover.genre_catalog import GENRE_PROFILES, genre_key, genre_prompt_core
from backend.cover.style_prompt import generate_cover_styles
from backend.cover.suno_cover import cover_styles_for_project


class GenreCatalogTests(unittest.TestCase):
    def test_every_profile_has_complete_prompt_form(self):
        for key, profile in GENRE_PROFILES.items():
            prompt = genre_prompt_core(key)
            with self.subTest(key=key):
                self.assertIn(profile["label"], prompt)
                self.assertIn(profile["bpm"], prompt)
                self.assertIn(profile["groove"], prompt)
                self.assertIn(profile["music"], prompt)
                self.assertIn(profile["arrangement"], prompt)
                self.assertIn(profile["mix"], prompt)
                self.assertIn(profile["avoid"], prompt)

    def test_specific_house_subgenres_are_not_collapsed(self):
        self.assertEqual("deep house", genre_key("Deep House"))
        self.assertEqual("future house", genre_key("Future House"))
        self.assertEqual("tropical house", genre_key("Tropical House"))
        self.assertEqual("house", genre_key("House"))

    def test_music_line_is_market_modifier_not_second_genre(self):
        prompt = cover_styles_for_project("Deep House", music_line="Korean")
        self.assertIn("Deep House vocal cover", prompt)
        self.assertIn("Korean-market polish", prompt)
        self.assertNotIn("K-pop", prompt)

    def test_selected_genre_wins_over_description(self):
        prompt = cover_styles_for_project(
            "Deep House", description="khung cảnh ballad buồn", music_line="US-UK")
        self.assertIn("118-124 BPM", prompt)
        self.assertNotIn("Ballad vocal cover", prompt)

    def test_project_description_cannot_authorize_second_genre(self):
        # Description là ý tưởng/mood, không phải nơi chọn genre.
        prompt, source = generate_cover_styles(
            "Deep House", description="Latin sunset", music_line="US-UK",
            api_config=SimpleNamespace(api_key=None))
        self.assertEqual("fallback:no-key", source)
        self.assertIn("Deep House vocal cover", prompt)
        self.assertNotIn("Latin", prompt)

    def test_fallback_preserves_full_profile_and_lyrics_lock(self):
        prompt, source = generate_cover_styles(
            "Vietmix", music_line="VN", api_config=SimpleNamespace(api_key=None))
        self.assertEqual("fallback:no-key", source)
        self.assertIn("124-128 BPM", prompt)
        self.assertIn("Vietnamese-market polish", prompt)
        self.assertIn("preserve the supplied lyrics exactly", prompt)
        self.assertLessEqual(len(prompt), 1000)


if __name__ == "__main__":
    unittest.main()
