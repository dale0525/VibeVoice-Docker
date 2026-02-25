import unittest

from vibevoice_docker.cosyvoice_adapter import build_cosy_prompt_text, speaker_script_to_cosy_text


class TestCosyVoiceAdapter(unittest.TestCase):
    def test_single_speaker_script_to_plain_text(self) -> None:
        script = "Speaker 0: 你好。\nSpeaker0: 再见。"
        out = speaker_script_to_cosy_text(script)
        self.assertEqual("你好。 再见。", out)

    def test_plain_text_passthrough(self) -> None:
        out = speaker_script_to_cosy_text("  这是普通文本  ")
        self.assertEqual("这是普通文本", out)

    def test_prompt_text_prefers_user_value(self) -> None:
        prompt = build_cosy_prompt_text("这是参考文本。", "目标文本。")
        self.assertIn("<|endofprompt|>", prompt)
        self.assertTrue(prompt.endswith("这是参考文本。"))

    def test_prompt_text_falls_back_to_tts_excerpt(self) -> None:
        prompt = build_cosy_prompt_text("", "第一句。第二句。")
        self.assertIn("<|endofprompt|>", prompt)
        self.assertTrue(prompt.endswith("第一句。"))

    def test_prompt_text_keeps_existing_endofprompt_token(self) -> None:
        raw = "你是一个语音助手。<|endofprompt|>这是参考文本。"
        prompt = build_cosy_prompt_text(raw, "目标文本。")
        self.assertEqual(raw, prompt)
