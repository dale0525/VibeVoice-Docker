import unittest

from vibevoice_docker.settings import _normalize_model_id


class TestNormalizeModelId(unittest.TestCase):
    def test_keeps_vibevoice_aliases(self) -> None:
        self.assertEqual("vibevoice-1.5b", _normalize_model_id("1.5b", "vibevoice-7b"))
        self.assertEqual("vibevoice-7b", _normalize_model_id("7b", "vibevoice-1.5b"))

    def test_supports_moss_ttsd_aliases(self) -> None:
        self.assertEqual("moss-ttsd-v1.0", _normalize_model_id("moss-ttsd-v1.0", "vibevoice-1.5b"))
        self.assertEqual("moss-ttsd-v1.0", _normalize_model_id("moss_ttsd", "vibevoice-1.5b"))
        self.assertEqual("moss-ttsd-v1.0", _normalize_model_id("moss", "vibevoice-1.5b"))

    def test_unknown_value_falls_back_to_default(self) -> None:
        self.assertEqual("vibevoice-7b", _normalize_model_id("unknown-model", "vibevoice-7b"))

