import unittest

from vibevoice_docker.moss_adapter import build_moss_prompt_text, speaker_script_to_moss_text


class TestMossAdapter(unittest.TestCase):
    def test_single_speaker_script_to_moss_text(self) -> None:
        script = "Speaker 0: 你好。\nSpeaker0: 再见。"
        out = speaker_script_to_moss_text(script)
        self.assertEqual("[S1] 你好。 [S1] 再见。", out)

    def test_plain_text_to_moss_text(self) -> None:
        out = speaker_script_to_moss_text("这是普通文本")
        self.assertEqual("[S1] 这是普通文本", out)

    def test_prompt_text_prefers_user_value(self) -> None:
        prompt = build_moss_prompt_text("[S1] This is a prompt.", "[S1] 目标文本")
        self.assertEqual("[S1] This is a prompt.", prompt)

    def test_prompt_text_falls_back_to_dialogue_excerpt(self) -> None:
        prompt = build_moss_prompt_text("", "[S1] 第一段。 [S1] 第二段。")
        self.assertTrue(prompt.startswith("[S1] "))
        self.assertIn("第一段", prompt)

