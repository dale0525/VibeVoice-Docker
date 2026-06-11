import os
import unittest

from vibevoice_docker.settings import Settings


class TestSettingsEnv(unittest.TestCase):
    def setUp(self) -> None:
        self._snapshot = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._snapshot)

    def test_model_id_reads_model_env(self) -> None:
        os.environ.pop("MODEL_ID", None)
        os.environ["MODEL"] = "7b"
        settings = Settings.load()
        self.assertEqual("vibevoice-7b", settings.model_id)

    def test_model_id_prefers_model_id_env(self) -> None:
        os.environ["MODEL"] = "7b"
        os.environ["MODEL_ID"] = "cosyvoice3-0.5b"
        settings = Settings.load()
        self.assertEqual("cosyvoice3-0.5b", settings.model_id)

    def test_removed_moss_model_id_falls_back_to_default(self) -> None:
        os.environ["MODEL_ID"] = "moss-ttsd-v1.0"
        settings = Settings.load()
        self.assertEqual("vibevoice-1.5b", settings.model_id)

    def test_vibevoice_sampling_defaults_when_env_missing(self) -> None:
        os.environ.pop("VIBEVOICE_DEFAULT_SEED", None)
        os.environ.pop("VIBEVOICE_DEFAULT_TEMPERATURE", None)
        settings = Settings.load()
        self.assertEqual(42, settings.vibevoice_default_seed)
        self.assertEqual(0.0, settings.vibevoice_default_temperature)

    def test_vibevoice_sampling_defaults_can_be_overridden(self) -> None:
        os.environ["VIBEVOICE_DEFAULT_SEED"] = "123"
        os.environ["VIBEVOICE_DEFAULT_TEMPERATURE"] = "0.65"
        settings = Settings.load()
        self.assertEqual(123, settings.vibevoice_default_seed)
        self.assertEqual(0.65, settings.vibevoice_default_temperature)

    def test_inference_accelerator_defaults_to_auto(self) -> None:
        os.environ.pop("TTS_ACCELERATOR", None)
        os.environ.pop("INFERENCE_ACCELERATOR", None)
        settings = Settings.load()
        self.assertEqual("auto", settings.inference_accelerator)

    def test_inference_accelerator_can_be_overridden(self) -> None:
        os.environ["TTS_ACCELERATOR"] = "metal"
        settings = Settings.load()
        self.assertEqual("mps", settings.inference_accelerator)

    def test_cosyvoice3_acceleration_flags_default_off(self) -> None:
        os.environ.pop("COSYVOICE3_LOAD_TRT", None)
        os.environ.pop("COSYVOICE3_LOAD_VLLM", None)
        settings = Settings.load()
        self.assertFalse(settings.cosyvoice3_load_trt)
        self.assertFalse(settings.cosyvoice3_load_vllm)

    def test_cosyvoice3_acceleration_flags_can_be_enabled(self) -> None:
        os.environ["COSYVOICE3_LOAD_TRT"] = "true"
        os.environ["COSYVOICE3_LOAD_VLLM"] = "1"
        settings = Settings.load()
        self.assertTrue(settings.cosyvoice3_load_trt)
        self.assertTrue(settings.cosyvoice3_load_vllm)
