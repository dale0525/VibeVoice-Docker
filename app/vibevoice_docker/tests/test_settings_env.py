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
        os.environ["MODEL_ID"] = "moss-ttsd-v1.0"
        settings = Settings.load()
        self.assertEqual("moss-ttsd-v1.0", settings.model_id)
