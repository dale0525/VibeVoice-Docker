import asyncio
import importlib
import sys
import tempfile
import types
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch


class _FakeTensor:
    def to(self, *_args, **_kwargs):
        return self


class _FakeGenerator:
    def __init__(self, *_args, **_kwargs) -> None:
        self.seed: int | None = None

    def manual_seed(self, seed: int):
        self.seed = int(seed)
        return self


class _FakeProcessor:
    def __init__(self) -> None:
        self.tokenizer = object()

    def __call__(self, **_kwargs):
        return {"input_ids": _FakeTensor()}


class _FakeModel:
    def __init__(self) -> None:
        self.last_generate_kwargs: dict | None = None

    def generate(self, **kwargs):
        self.last_generate_kwargs = kwargs
        return types.SimpleNamespace(speech_outputs=[[0.25, -0.5]])


class TestMainSamplingControls(unittest.TestCase):
    def setUp(self) -> None:
        self._torch_patch = None
        try:
            __import__("numpy")
        except ModuleNotFoundError as exc:
            self.skipTest(f"test dependencies missing: {exc}")

        try:
            __import__("torch")
        except ModuleNotFoundError:
            fake_torch = types.SimpleNamespace(
                cuda=types.SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None),
                dtype=type("dtype", (), {}),
                float16=object(),
                bfloat16=object(),
                float32=object(),
                Tensor=object,
                is_tensor=lambda _value: isinstance(_value, _FakeTensor),
                manual_seed=lambda _seed: None,
                Generator=_FakeGenerator,
            )
            self._torch_patch = patch.dict(sys.modules, {"torch": fake_torch})
            self._torch_patch.start()

        try:
            self.api_main = importlib.import_module("main")
        except ModuleNotFoundError as exc:
            self.skipTest(f"test dependencies missing: {exc}")

    def tearDown(self) -> None:
        if self._torch_patch is not None:
            self._torch_patch.stop()

    def test_create_speech_forwards_seed_and_temperature(self) -> None:
        payload = self.api_main.SpeechRequest(
            input="你好",
            voice="zh-Xinran_woman",
            response_format="wav",
            seed=42,
            temperature=0.6,
        )
        expected_response = self.api_main.Response(content=b"ok", media_type="audio/wav")

        with patch.object(
            self.api_main,
            "_synthesize_with_voice",
            new=AsyncMock(return_value=expected_response),
        ) as synth_mock:
            response = asyncio.run(self.api_main.create_speech(payload, None))

        self.assertIs(response, expected_response)
        self.assertEqual(42, synth_mock.await_args.kwargs.get("seed"))
        self.assertEqual(0.6, synth_mock.await_args.kwargs.get("temperature"))

    def test_run_inference_vibevoice_applies_temperature_and_seed(self) -> None:
        manual_seed_calls: list[int] = []
        cuda_seed_calls: list[int] = []
        fake_torch = types.SimpleNamespace(
            cuda=types.SimpleNamespace(
                is_available=lambda: True,
                manual_seed_all=lambda seed: cuda_seed_calls.append(int(seed)),
            ),
            is_tensor=lambda value: isinstance(value, _FakeTensor),
            manual_seed=lambda seed: manual_seed_calls.append(int(seed)),
            Generator=_FakeGenerator,
        )

        fake_model = _FakeModel()
        loaded = types.SimpleNamespace(
            processor=_FakeProcessor(),
            model=fake_model,
            device="cpu",
            sample_rate=24000,
        )
        with tempfile.TemporaryDirectory() as tmp:
            voice = self.api_main.Voice(
                id="v",
                name="v",
                type="custom",
                sample_path=Path(tmp) / "sample.wav",
                created_at=0,
                prompt_text=None,
            )

            with patch.dict(sys.modules, {"torch": fake_torch}):
                audio, sample_rate = self.api_main._run_inference_vibevoice(
                    loaded,
                    script="Speaker 0: hello",
                    voice=voice,
                    cfg_scale=3.0,
                    seed=7,
                    temperature=0.9,
                )

        self.assertEqual(24000, sample_rate)
        self.assertEqual([0.25, -0.5], audio)
        self.assertEqual([7], manual_seed_calls)
        self.assertEqual([7], cuda_seed_calls)
        assert fake_model.last_generate_kwargs is not None
        self.assertEqual(3.0, fake_model.last_generate_kwargs["cfg_scale"])
        self.assertEqual(
            {"do_sample": True, "temperature": 0.9},
            fake_model.last_generate_kwargs["generation_config"],
        )

    def test_synthesize_with_voice_rejects_seed_temperature_for_cosyvoice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            voice = self.api_main.Voice(
                id="ref",
                name="ref",
                type="custom",
                sample_path=Path(tmp) / "sample.wav",
                created_at=0,
                prompt_text=None,
            )
            cosy_settings = replace(self.api_main.settings, model_id="cosyvoice3-0.5b")
            with patch.object(self.api_main, "settings", cosy_settings):
                with self.assertRaises(self.api_main.HTTPException) as ctx:
                    asyncio.run(
                        self.api_main._synthesize_with_voice(
                            input_text="hello",
                            default_voice_id=voice.id,
                            response_format="wav",
                            cfg_scale=3.0,
                            default_voice=voice,
                            seed=1,
                            temperature=0.7,
                        )
                    )

        self.assertEqual(400, ctx.exception.status_code)
        self.assertIn("cosyvoice3", str(ctx.exception.detail).lower())

    def test_synthesize_with_voice_uses_vibevoice_defaults_when_params_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            voice = self.api_main.Voice(
                id="ref",
                name="ref",
                type="custom",
                sample_path=Path(tmp) / "sample.wav",
                created_at=0,
                prompt_text=None,
            )
            vibe_settings = replace(
                self.api_main.settings,
                model_id="vibevoice-1.5b",
                vibevoice_default_seed=123,
                vibevoice_default_temperature=0.35,
            )

            with patch.object(self.api_main, "settings", vibe_settings):
                with patch.object(
                    self.api_main,
                    "_normalize_request_segments",
                    return_value=[(voice.id, "hello")],
                ):
                    with patch.object(
                        self.api_main,
                        "_resolve_voice_segments",
                        return_value=[(voice, "hello")],
                    ):
                        with patch.object(
                            self.api_main,
                            "audio_to_wav_bytes",
                            return_value=b"wav-bytes",
                        ):
                            with patch.object(
                                self.api_main,
                                "_run_inference_segments",
                                return_value=([0.0, 0.1], 24000),
                            ) as run_mock:
                                response = asyncio.run(
                                    self.api_main._synthesize_with_voice(
                                        input_text="hello",
                                        default_voice_id=voice.id,
                                        response_format="wav",
                                        cfg_scale=3.0,
                                        default_voice=voice,
                                    )
                                )

        self.assertEqual("audio/wav", response.media_type)
        self.assertEqual(123, run_mock.call_args.args[3])
        self.assertEqual(0.35, run_mock.call_args.args[4])
