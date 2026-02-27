import os
import unittest

from vibevoice_docker.text_normalize import normalize_script_to_voice_segments, normalize_single_speaker_script


class TestNormalizeScriptToVoiceSegments(unittest.TestCase):
    def setUp(self) -> None:
        self._old_limit = os.environ.get("SCRIPT_LINE_MAX_CHARS")

    def tearDown(self) -> None:
        if self._old_limit is None:
            os.environ.pop("SCRIPT_LINE_MAX_CHARS", None)
        else:
            os.environ["SCRIPT_LINE_MAX_CHARS"] = self._old_limit

    def test_allows_multiple_speakers_in_speaker_script(self) -> None:
        script = "Speaker 0: hello\nSpeaker 1: world"
        out = normalize_single_speaker_script(script, enable_cn_punct_normalize=False)
        self.assertEqual(script, out)

    def test_voice_tag_script_uses_tagged_voice_and_continuation_lines(self) -> None:
        script = "[voice_a]第一句\n第二句\n[voice_b]第三句"
        out = normalize_script_to_voice_segments(
            script,
            default_voice_id="api_voice",
            enable_cn_punct_normalize=False,
        )
        self.assertEqual(
            [
                ("voice_a", "第一句"),
                ("voice_a", "第二句"),
                ("voice_b", "第三句"),
            ],
            out,
        )

    def test_voice_tag_script_uses_default_voice_before_first_tag(self) -> None:
        script = "默认第一句\n[voice_b]第二句"
        out = normalize_script_to_voice_segments(
            script,
            default_voice_id="api_voice",
            enable_cn_punct_normalize=False,
        )
        self.assertEqual(
            [
                ("api_voice", "默认第一句"),
                ("voice_b", "第二句"),
            ],
            out,
        )

    def test_speaker_script_without_voice_tags_falls_back_to_default_voice(self) -> None:
        script = "Speaker 0: 第一位\nSpeaker 1: 第二位"
        out = normalize_script_to_voice_segments(
            script,
            default_voice_id="api_voice",
            enable_cn_punct_normalize=False,
        )
        self.assertEqual(
            [
                ("api_voice", "第一位"),
                ("api_voice", "第二位"),
            ],
            out,
        )

    def test_voice_tag_script_respects_max_chars_per_line(self) -> None:
        os.environ["SCRIPT_LINE_MAX_CHARS"] = "5"

        script = "[voice_a]ABCDEFGHIJKL"
        out = normalize_script_to_voice_segments(
            script,
            default_voice_id="api_voice",
            enable_cn_punct_normalize=False,
        )

        self.assertEqual(3, len(out))
        self.assertTrue(all(voice_id == "voice_a" for voice_id, _ in out))
        self.assertTrue(all(len(text) <= 5 for _, text in out))
        self.assertEqual("ABCDEFGHIJKL", "".join(text for _, text in out))
