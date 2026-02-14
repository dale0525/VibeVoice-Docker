import importlib
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - depends on local env
    TestClient = None  # type: ignore


class TestReferenceSpeechEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        if TestClient is None:
            self.skipTest("fastapi is not installed in local test environment")

        try:
            self.api_main = importlib.import_module("main")
        except ModuleNotFoundError as exc:
            self.skipTest(f"test dependencies missing: {exc}")

        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        builtin_dir = root / "builtin-voices"
        custom_dir = root / "custom-voices"
        builtin_dir.mkdir(parents=True, exist_ok=True)
        custom_dir.mkdir(parents=True, exist_ok=True)
        (builtin_dir / "builtin-test.wav").write_bytes(b"builtin-audio-bytes")

        self.seed_sample = root / "seed.wav"
        self.seed_sample.write_bytes(b"seed-custom-audio")

        self.voice_store = self.api_main.VoiceStore(builtin_dir=builtin_dir, custom_dir=custom_dir)
        self.created_voice = self.voice_store.create_voice(
            name="test-custom",
            sample_wav_path=self.seed_sample,
            prompt_text="old prompt",
        )

        patched_settings = replace(
            self.api_main.settings,
            data_dir=root,
            builtin_voices_dir=builtin_dir,
            voices_dir=custom_dir,
        )

        self._settings_patcher = patch.object(self.api_main, "settings", patched_settings)
        self._voice_store_patcher = patch.object(self.api_main, "voice_store", self.voice_store)
        self._ffmpeg_patcher = patch.object(
            self.api_main,
            "_ffmpeg_to_wav_24k_mono",
            side_effect=lambda src, dst: shutil.copy2(src, dst),
        )
        self._inference_patcher = patch.object(
            self.api_main,
            "_run_inference",
            return_value=([0.0] * 2400, 24000),
        )

        self._settings_patcher.start()
        self._voice_store_patcher.start()
        self._ffmpeg_patcher.start()
        self._inference_patcher.start()
        self.client = TestClient(self.api_main.app)

    def tearDown(self) -> None:
        if hasattr(self, "_inference_patcher"):
            self._inference_patcher.stop()
        if hasattr(self, "_ffmpeg_patcher"):
            self._ffmpeg_patcher.stop()
        if hasattr(self, "_voice_store_patcher"):
            self._voice_store_patcher.stop()
        if hasattr(self, "_settings_patcher"):
            self._settings_patcher.stop()
        if hasattr(self, "_tmpdir"):
            self._tmpdir.cleanup()

    def test_reference_speech_success(self) -> None:
        response = self.client.post(
            "/v1/audio/speech/reference",
            data={
                "input": "你好，世界",
                "response_format": "wav",
                "prompt_text": "这是参考音频文本",
            },
            files={"file": ("ref.wav", b"fake-audio-bytes", "audio/wav")},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("audio/wav", response.headers.get("content-type"))
        self.assertGreater(len(response.content), 0)

    def test_reference_speech_empty_input(self) -> None:
        response = self.client.post(
            "/v1/audio/speech/reference",
            data={"input": "   ", "response_format": "wav"},
            files={"file": ("ref.wav", b"fake-audio-bytes", "audio/wav")},
        )

        self.assertEqual(400, response.status_code)
        payload = response.json()
        self.assertIn("input is required", str(payload))

    def test_get_voice_sample_success(self) -> None:
        response = self.client.get(f"/v1/voices/{self.created_voice.id}/sample")
        self.assertEqual(200, response.status_code)
        self.assertEqual("audio/wav", response.headers.get("content-type"))
        self.assertGreater(len(response.content), 0)

    def test_update_custom_voice_prompt_text(self) -> None:
        response = self.client.patch(
            f"/v1/voices/{self.created_voice.id}",
            json={"prompt_text": "updated prompt"},
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("updated prompt", payload.get("prompt_text"))

        fetched = self.voice_store.get_voice(self.created_voice.id)
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual("updated prompt", fetched.prompt_text)

    def test_update_builtin_voice_rejected(self) -> None:
        response = self.client.patch(
            "/v1/voices/builtin-test",
            json={"prompt_text": "not allowed"},
        )
        self.assertEqual(400, response.status_code)
