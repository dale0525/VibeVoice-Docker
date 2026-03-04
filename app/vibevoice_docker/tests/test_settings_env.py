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
