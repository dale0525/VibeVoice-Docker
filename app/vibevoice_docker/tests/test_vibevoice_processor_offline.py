import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


class _DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


class _StubModules:
    def __init__(self, tokenizer_calls):
        self._tokenizer_calls = tokenizer_calls
        self._previous: dict[str, types.ModuleType | None] = {}

    def _set_module(self, name: str, module: types.ModuleType) -> None:
        self._previous[name] = sys.modules.get(name)
        sys.modules[name] = module

    def install(self, repo_root: Path) -> Path:
        vibevoice_root = repo_root / "VibeVoice" / "vibevoice"
        processor_root = vibevoice_root / "processor"
        modular_root = vibevoice_root / "modular"

        numpy_mod = types.ModuleType("numpy")
        numpy_mod.ndarray = list
        numpy_mod.float32 = float
        numpy_mod.bool_ = bool
        numpy_mod.array = lambda value, dtype=None: value
        self._set_module("numpy", numpy_mod)

        torch_mod = types.ModuleType("torch")
        torch_mod.Tensor = type("Tensor", (), {})
        torch_mod.device = str
        torch_mod.dtype = type("dtype", (), {})
        torch_mod.float32 = "float32"
        torch_mod.bool = "bool"
        torch_mod.long = "long"
        torch_mod.tensor = lambda value, **kwargs: value
        self._set_module("torch", torch_mod)

        tokenization_utils_mod = types.ModuleType("transformers.tokenization_utils_base")
        tokenization_utils_mod.BatchEncoding = dict
        tokenization_utils_mod.PaddingStrategy = type("PaddingStrategy", (), {})
        tokenization_utils_mod.PreTokenizedInput = object
        tokenization_utils_mod.TextInput = object
        tokenization_utils_mod.TruncationStrategy = object
        self._set_module("transformers.tokenization_utils_base", tokenization_utils_mod)

        transformers_utils_mod = types.ModuleType("transformers.utils")
        transformers_utils_mod.TensorType = object
        transformers_utils_mod.cached_file = lambda *args, **kwargs: ""
        transformers_utils_mod.logging = types.SimpleNamespace(
            get_logger=lambda *_: _DummyLogger()
        )
        self._set_module("transformers.utils", transformers_utils_mod)

        transformers_mod = types.ModuleType("transformers")
        transformers_mod.tokenization_utils_base = tokenization_utils_mod
        transformers_mod.utils = transformers_utils_mod
        self._set_module("transformers", transformers_mod)

        vibevoice_pkg = types.ModuleType("vibevoice")
        vibevoice_pkg.__path__ = [str(vibevoice_root)]
        self._set_module("vibevoice", vibevoice_pkg)

        processor_pkg = types.ModuleType("vibevoice.processor")
        processor_pkg.__path__ = [str(processor_root)]
        self._set_module("vibevoice.processor", processor_pkg)

        modular_pkg = types.ModuleType("vibevoice.modular")
        modular_pkg.__path__ = [str(modular_root)]
        self._set_module("vibevoice.modular", modular_pkg)

        tokenizer_processor_mod = types.ModuleType("vibevoice.processor.vibevoice_tokenizer_processor")

        class AudioNormalizer:
            def __call__(self, audio):
                return audio

        class VibeVoiceTokenizerProcessor:
            model_input_names: list[str] = []

            def __init__(self, **kwargs):
                self.kwargs = kwargs

        tokenizer_processor_mod.AudioNormalizer = AudioNormalizer
        tokenizer_processor_mod.VibeVoiceTokenizerProcessor = VibeVoiceTokenizerProcessor
        self._set_module("vibevoice.processor.vibevoice_tokenizer_processor", tokenizer_processor_mod)

        tokenizer_mod = types.ModuleType("vibevoice.modular.modular_vibevoice_text_tokenizer")
        calls = self._tokenizer_calls

        class VibeVoiceTextTokenizerFast:
            @classmethod
            def from_pretrained(cls, source, **kwargs):
                calls.append((source, dict(kwargs)))
                return cls()

        tokenizer_mod.VibeVoiceTextTokenizer = VibeVoiceTextTokenizerFast
        tokenizer_mod.VibeVoiceTextTokenizerFast = VibeVoiceTextTokenizerFast
        self._set_module("vibevoice.modular.modular_vibevoice_text_tokenizer", tokenizer_mod)

        return processor_root / "vibevoice_processor.py"

    def restore(self) -> None:
        for name, old in reversed(list(self._previous.items())):
            if old is None:
                sys.modules.pop(name, None)
                continue
            sys.modules[name] = old


class TestVibeVoiceProcessorOffline(unittest.TestCase):
    def setUp(self) -> None:
        self._tokenizer_calls: list[tuple[str, dict]] = []
        self._stub_modules = _StubModules(self._tokenizer_calls)
        self._repo_root = Path(__file__).resolve().parents[3]
        self._module_path = self._stub_modules.install(self._repo_root)

        spec = importlib.util.spec_from_file_location(
            "vibevoice.processor.vibevoice_processor",
            self._module_path,
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self._module = module

    def tearDown(self) -> None:
        self._stub_modules.restore()

    def test_prefers_local_model_dir_for_tokenizer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            config_path = model_dir / "preprocessor_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "language_model_pretrained_name": "Qwen/Qwen2.5-7B",
                        "audio_processor": {},
                    }
                ),
                encoding="utf-8",
            )

            self._module.VibeVoiceProcessor.from_pretrained(str(model_dir))

        self.assertTrue(self._tokenizer_calls, "expected tokenizer to be loaded")
        source, kwargs = self._tokenizer_calls[0]
        self.assertEqual(str(model_dir), source)
        self.assertTrue(kwargs.get("local_files_only"))
