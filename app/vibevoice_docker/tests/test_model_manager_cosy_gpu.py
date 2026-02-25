import unittest
from pathlib import Path
from types import SimpleNamespace

try:
    from vibevoice_docker.model_manager import ModelManager
except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
    if exc.name == "torch":
        ModelManager = None  # type: ignore[assignment]
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
