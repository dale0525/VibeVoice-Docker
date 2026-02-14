import tempfile
import unittest
from pathlib import Path

from vibevoice_docker.voices import VoiceStore


class TestVoiceStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        self.builtin_dir = root / "builtin"
        self.custom_dir = root / "custom"
        self.builtin_dir.mkdir(parents=True, exist_ok=True)
        self.custom_dir.mkdir(parents=True, exist_ok=True)

        (self.builtin_dir / "builtin-voice.wav").write_bytes(b"fake-builtin-audio")
        self.sample_path = root / "sample.wav"
        self.sample_path.write_bytes(b"fake-custom-audio")

        self.store = VoiceStore(builtin_dir=self.builtin_dir, custom_dir=self.custom_dir)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_create_and_update_custom_voice_prompt_text(self) -> None:
        created = self.store.create_voice(
            name="my-voice",
            sample_wav_path=self.sample_path,
            prompt_text="first prompt",
        )
        self.assertEqual("first prompt", created.prompt_text)

        updated = self.store.update_voice_prompt_text(created.id, "updated prompt")
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual("updated prompt", updated.prompt_text)

        fetched = self.store.get_voice(created.id)
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual("updated prompt", fetched.prompt_text)

    def test_update_prompt_text_to_empty_becomes_none(self) -> None:
        created = self.store.create_voice(
            name="my-voice",
            sample_wav_path=self.sample_path,
            prompt_text="has value",
        )
        updated = self.store.update_voice_prompt_text(created.id, "   ")
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertIsNone(updated.prompt_text)

    def test_update_missing_voice_returns_none(self) -> None:
        self.assertIsNone(self.store.update_voice_prompt_text("missing-voice", "anything"))

