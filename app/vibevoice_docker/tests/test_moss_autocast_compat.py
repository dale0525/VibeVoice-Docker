import unittest

from vibevoice_docker import torch_compat


class _LegacyTorch:
    def __init__(self) -> None:
        self.calls = 0

    def is_autocast_enabled(self):
        self.calls += 1
        return False


class _ModernTorch:
    def is_autocast_enabled(self, device_type=None):  # pragma: no cover - signature probe only
        return device_type is not None


class TestMossAutocastCompat(unittest.TestCase):
    def test_adds_device_type_support_for_legacy_torch(self) -> None:
        torch_mod = _LegacyTorch()

        installed = torch_compat.ensure_is_autocast_enabled_device_type_support(torch_mod=torch_mod)
        self.assertTrue(installed)

        self.assertFalse(torch_mod.is_autocast_enabled("cuda"))
        self.assertEqual(1, torch_mod.calls)

        self.assertFalse(torch_compat.ensure_is_autocast_enabled_device_type_support(torch_mod=torch_mod))

    def test_keeps_modern_signature_unchanged(self) -> None:
        torch_mod = _ModernTorch()
        self.assertFalse(torch_compat.ensure_is_autocast_enabled_device_type_support(torch_mod=torch_mod))
