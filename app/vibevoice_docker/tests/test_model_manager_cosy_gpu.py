import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    from vibevoice_docker.model_manager import ModelManager
    import torch
except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
    if exc.name == "torch":
        ModelManager = None  # type: ignore[assignment]
        torch = None  # type: ignore[assignment]
    else:
        raise


class _FakeSession:
    def __init__(self, providers):
        self._providers = providers

    def get_providers(self):
        return list(self._providers)


@unittest.skipIf(ModelManager is None, "torch is not installed in local test environment")
class TestModelManagerCosyGpu(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = ModelManager(models_dir=Path("."), idle_unload_seconds=60, max_loaded_models=1)

    def test_accepts_cuda_execution_provider(self) -> None:
        fake_model = SimpleNamespace(
            frontend=SimpleNamespace(
                speech_tokenizer_session=_FakeSession(["CUDAExecutionProvider", "CPUExecutionProvider"])
            )
        )
        self.manager._ensure_cosyvoice3_cuda_provider(fake_model, device="cuda")

    def test_rejects_cpu_fallback_when_device_is_cuda(self) -> None:
        fake_model = SimpleNamespace(
            frontend=SimpleNamespace(
                speech_tokenizer_session=_FakeSession(["CPUExecutionProvider"])
            )
        )
        with self.assertRaisesRegex(RuntimeError, "fall back to CPU"):
            self.manager._ensure_cosyvoice3_cuda_provider(fake_model, device="cuda")

    def test_skips_check_when_device_is_cpu(self) -> None:
        fake_model = SimpleNamespace(
            frontend=SimpleNamespace(
                speech_tokenizer_session=_FakeSession(["CPUExecutionProvider"])
            )
        )
        self.manager._ensure_cosyvoice3_cuda_provider(fake_model, device="cpu")

    def test_auto_selects_mps_for_vibevoice_when_cuda_is_absent(self) -> None:
        with (
            patch.object(self.manager, "_cuda_available", return_value=False),
            patch.object(self.manager, "_mps_available", return_value=True),
        ):
            self.assertEqual("mps", self.manager._pick_device("vibevoice"))

    def test_auto_keeps_cosyvoice3_on_cpu_when_only_mps_is_available(self) -> None:
        with (
            patch.object(self.manager, "_cuda_available", return_value=False),
            patch.object(self.manager, "_mps_available", return_value=True),
        ):
            self.assertEqual("cpu", self.manager._pick_device("cosyvoice3"))

    def test_rejects_explicit_mps_for_cosyvoice3(self) -> None:
        manager = ModelManager(
            models_dir=Path("."),
            idle_unload_seconds=60,
            max_loaded_models=1,
            inference_accelerator="mps",
        )
        with self.assertRaisesRegex(RuntimeError, "VibeVoice backend"):
            manager._pick_device("cosyvoice3")

    def test_rejects_cosyvoice3_trt_without_cuda_before_importing_backend(self) -> None:
        manager = ModelManager(
            models_dir=Path("."),
            idle_unload_seconds=60,
            max_loaded_models=1,
            cosyvoice3_load_trt=True,
        )
        with self.assertRaisesRegex(RuntimeError, "requires CUDA"):
            manager._load_cosyvoice3(Path("."), device="cpu", dtype=torch.float32)
