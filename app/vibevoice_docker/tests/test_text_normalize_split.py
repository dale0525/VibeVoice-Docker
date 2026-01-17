import os
import unittest

from vibevoice_docker.text_normalize import normalize_single_speaker_script


class TestNormalizeSingleSpeakerScriptSplit(unittest.TestCase):
    def setUp(self) -> None:
        self._old_limit = os.environ.get("VIBEVOICE_SCRIPT_LINE_MAX_CHARS")

    def tearDown(self) -> None:
        if self._old_limit is None:
            os.environ.pop("VIBEVOICE_SCRIPT_LINE_MAX_CHARS", None)
        else:
            os.environ["VIBEVOICE_SCRIPT_LINE_MAX_CHARS"] = self._old_limit

    def test_splits_when_exceeds_max_chars(self) -> None:
        os.environ["VIBEVOICE_SCRIPT_LINE_MAX_CHARS"] = "20"

        text = "A" * 60
        script = f"Speaker 0: {text}"
        out = normalize_single_speaker_script(script, enable_cn_punct_normalize=False)

        lines = out.splitlines()
        self.assertEqual(3, len(lines))

        parts: list[str] = []
        for line in lines:
            self.assertTrue(line.startswith("Speaker 0: "))
            part = line.split(":", 1)[1].strip()
            self.assertLessEqual(len(part), 20)
            parts.append(part)

        self.assertEqual(text, "".join(parts))

    def test_does_not_split_when_under_limit(self) -> None:
        os.environ["VIBEVOICE_SCRIPT_LINE_MAX_CHARS"] = "20"

        text = "A" * 20
        script = f"Speaker 0: {text}"
        out = normalize_single_speaker_script(script, enable_cn_punct_normalize=False)
        self.assertEqual(1, len(out.splitlines()))

    def test_does_not_split_on_comma_when_no_period_in_window(self) -> None:
        os.environ["VIBEVOICE_SCRIPT_LINE_MAX_CHARS"] = "10"

        text = "AAAAA,BBBBBCCCCCC."
        script = f"Speaker 0: {text}"
        out = normalize_single_speaker_script(script, enable_cn_punct_normalize=False)

        lines = out.splitlines()
        self.assertGreaterEqual(len(lines), 2)

        first_part = lines[0].split(":", 1)[1].strip()
        self.assertEqual("AAAAA,BBBB", first_part)
