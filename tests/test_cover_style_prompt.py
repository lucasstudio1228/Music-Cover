import json
import unittest
from types import SimpleNamespace
from unittest import mock

from backend.cover.style_prompt import (
    NO_CREATIVE_INSTRUMENT,
    enforce_vocal_first_styles,
    generate_cover_styles,
    style_signature,
)


class _Config:
    api_key = "test-key"
    model = "gpt-4.1"

    @staticmethod
    def to_client_kwargs():
        return {"api_key": "test-key", "base_url": "https://example.test/v1"}


def _client_returning(styles: str):
    response = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=json.dumps({"styles": styles})))])
    create = mock.MagicMock(return_value=response)
    return SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=create))), create


class CoverStylePromptTests(unittest.TestCase):
    def test_old_featured_solo_prompt_is_demoted_to_vocal_support(self):
        old = ("Deep House, featured trumpet, clearly audible melodic fills and a "
               "tasteful short solo, warm bass, extended instrumental break")
        guarded = enforce_vocal_first_styles(old)
        self.assertIn("supporting trumpet", guarded)
        self.assertIn("sparse low-level fills only between vocal phrases", guarded)
        self.assertNotIn("featured trumpet", guarded.casefold())
        self.assertNotIn("short solo", guarded.casefold())
        self.assertIn("continuous dominant lead singing", guarded)

    def test_ai_prompt_is_used_and_vietnamese_lyrics_are_locked(self):
        raw = ("Vietnamese neo-soul R&B cover, 82 BPM, syncopated pocket drums, "
               "warm sub-bass, lush Rhodes voicings, muted guitar accents, intimate "
               "breathy verses, soulful runs, layered dynamic chorus, sleek warm mix")
        client, create = _client_returning(raw)
        with mock.patch("openai.OpenAI", return_value=client):
            styles, source = generate_cover_styles(
                "R&B", "late-night heartbreak", "", "female", "Bài hát", "Ca sĩ",
                "Saxophone", api_config=_Config())
        self.assertEqual(source, "ai")
        self.assertIn("neo-soul R&B", styles)
        self.assertIn("female lead vocal", styles)
        self.assertIn("supporting saxophone", styles)
        self.assertIn("quantized to the existing groove", styles)
        self.assertIn("no stabs", styles)
        self.assertIn("percussion-like attacks", styles)
        self.assertIn("preserve the supplied lyrics exactly", styles)
        self.assertIn("lead vocal upfront and centered", styles)
        self.assertIn("3 dB above instrumental", styles)
        self.assertIn("instruments below voice", styles)
        self.assertLessEqual(len(styles), 1000)
        sent = create.call_args.kwargs["messages"][1]["content"]
        self.assertIn('"genre_SELECTED_BY_USER": "R&B"', sent)
        self.assertIn('"required_featured_instrument": "Saxophone"', sent)

    def test_instrumental_ai_mistake_falls_back_to_vocal_cover(self):
        raw = ("Purely instrumental only Deep House track with no vocals, 122 BPM, "
               "four-on-the-floor drums, deep bass and atmospheric pads for a club mix")
        client, _ = _client_returning(raw)
        with mock.patch("openai.OpenAI", return_value=client):
            styles, source = generate_cover_styles(
                "Deep House", api_config=_Config())
        self.assertTrue(source.startswith("fallback:"))
        self.assertIn("Deep House vocal cover", styles)
        self.assertIn("Vietnamese-market polish", styles)
        self.assertNotIn("instrumental only", styles.casefold())

    def test_no_key_uses_distinct_local_prompts_per_genre(self):
        cfg = SimpleNamespace(api_key=None)
        genres = ["Ballad", "Pop", "R&B", "Jazz", "Blues", "Lofi",
                  "Deep House", "Vietmix", "Remix"]
        prompts = [generate_cover_styles(g, api_config=cfg)[0] for g in genres]
        self.assertEqual(len(set(prompts)), len(genres))
        self.assertTrue(all("Vietnamese" in p for p in prompts))

    def test_signature_changes_with_genre_description_or_gender(self):
        base = style_signature("Ballad", "rain", "", "female")
        self.assertNotEqual(base, style_signature("Deep House", "rain", "", "female"))
        self.assertNotEqual(base, style_signature("Ballad", "sun", "", "female"))
        self.assertNotEqual(base, style_signature("Ballad", "rain", "", "male"))
        self.assertNotEqual(base, style_signature("Ballad", "rain", "", "female",
                                                  "Saxophone"))

    def test_flute_is_added_to_fallback_when_selected(self):
        styles, source = generate_cover_styles(
            "Ballad", featured_instrument="Sáo", api_config=SimpleNamespace(api_key=None))
        self.assertEqual(source, "fallback:no-key")
        self.assertIn("supporting flute", styles)
        self.assertIn("sparse fills between vocal phrases", styles)
        self.assertIn("no instrumental solos", styles)
        self.assertNotIn("short solo", styles.casefold())

    def test_default_uses_deterministic_safe_instrument_profile(self):
        raw = ("Vietnamese pop cover, 102 BPM, crisp drums, warm bass, bright guitar, "
               "supporting trumpet with sparse fills only between vocal phrases, clear "
               "dominant lead vocal, polished dynamic chorus and modern spacious mix")
        client, create = _client_returning(raw)
        with mock.patch("openai.OpenAI", return_value=client):
            styles, source = generate_cover_styles("Pop", api_config=_Config())
        self.assertEqual(source, "ai")
        self.assertIn("supporting soft sustained synthesizer pad", styles)
        self.assertIn("no off-grid hits", styles)
        self.assertIn("no instrumental solos", styles)
        sent = create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("soft sustained synthesizer pad", sent)
        self.assertIn("automatically selected from the genre-safe profile", sent)

    def test_default_fallback_also_adds_genre_suitable_instrument(self):
        styles, source = generate_cover_styles(
            "Jazz", api_config=SimpleNamespace(api_key=None))
        self.assertEqual(source, "fallback:no-key")
        self.assertIn("supporting muted Rhodes electric piano", styles)
        self.assertIn("quantized to the existing groove", styles)
        self.assertIn("preserve the supplied lyrics exactly", styles)
        self.assertIn("no lyrics in any other language", styles)
        self.assertLessEqual(len(styles), 1000)

    def test_unchecked_does_not_add_creative_instrument(self):
        styles, source = generate_cover_styles(
            "Jazz", featured_instrument=NO_CREATIVE_INSTRUMENT,
            api_config=SimpleNamespace(api_key=None))
        self.assertEqual(source, "fallback:no-key")
        self.assertNotIn("supporting saxophone", styles)
        self.assertNotIn("short solo", styles)

    def test_api_key_fragment_is_never_written_to_log(self):
        logs = []
        with mock.patch("openai.OpenAI",
                        side_effect=RuntimeError("Incorrect API key sk-ABC123_secret")):
            styles, source = generate_cover_styles(
                "Pop", api_config=_Config(), log=logs.append)
        self.assertTrue(source.startswith("fallback:"))
        self.assertIn("Pop vocal cover", styles)
        self.assertIn("Vietnamese-market polish", styles)
        joined = " ".join(logs)
        self.assertIn("API key bị từ chối", joined)
        self.assertNotIn("sk-ABC123", joined)


if __name__ == "__main__":
    unittest.main()
