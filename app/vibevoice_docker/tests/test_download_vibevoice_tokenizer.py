import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_module():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "download_vibevoice_tokenizer.py"
    spec = importlib.util.spec_from_file_location("download_vibevoice_tokenizer", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDownloadVibeVoiceTokenizer(unittest.TestCase):
    def test_normalize_model_id_aliases(self) -> None:
        mod = _load_module()
        self.assertEqual("vibevoice-1.5b", mod.normalize_model_id("1.5b"))
        self.assertEqual("vibevoice-7b", mod.normalize_model_id("7b"))
        self.assertEqual("cosyvoice3-0.5b", mod.normalize_model_id("cosy3"))

    def test_only_vibevoice_needs_tokenizer_prefetch(self) -> None:
        mod = _load_module()
        self.assertTrue(mod.is_vibevoice_model("vibevoice-1.5b"))
        self.assertTrue(mod.is_vibevoice_model("vibevoice-7b"))
        self.assertFalse(mod.is_vibevoice_model("cosyvoice3-0.5b"))

    def test_resolve_repo_prefers_preprocessor_config(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            (model_dir / "preprocessor_config.json").write_text(
                json.dumps({"language_model_pretrained_name": "Qwen/Qwen2.5-7B-Instruct"}),
                encoding="utf-8",
            )
            repo = mod.resolve_tokenizer_repo(model_id="vibevoice-7b", model_dir=model_dir)
        self.assertEqual("Qwen/Qwen2.5-7B-Instruct", repo)

    def test_resolve_repo_uses_default_when_config_missing(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            repo = mod.resolve_tokenizer_repo(model_id="vibevoice-7b", model_dir=model_dir)
        self.assertEqual("Qwen/Qwen2.5-7B", repo)

    def test_normalize_tokenizer_source_aliases(self) -> None:
        mod = _load_module()
        self.assertEqual("modelscope", mod.normalize_tokenizer_source(None))
        self.assertEqual("modelscope", mod.normalize_tokenizer_source("ms"))
        self.assertEqual("huggingface", mod.normalize_tokenizer_source("hf"))
        self.assertEqual("auto", mod.normalize_tokenizer_source("fallback"))

    def test_prefetch_tokenizer_saves_modelscope_tokenizer_to_model_dir(self) -> None:
        mod = _load_module()
        calls: list[str] = []

        class FakeTokenizer:
            def save_pretrained(self, output_dir: str) -> None:
                Path(output_dir, "tokenizer.json").write_text("{}", encoding="utf-8")

        class FakeAutoTokenizer:
            @staticmethod
            def from_pretrained(source: str):
                calls.append(source)
                return FakeTokenizer()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            model_dir = tmp / "model"
            model_dir.mkdir()
            source_dir = tmp / "source"
            source_dir.mkdir()
            fake_transformers = types.SimpleNamespace(AutoTokenizer=FakeAutoTokenizer)
            with (
                patch.dict(sys.modules, {"transformers": fake_transformers}),
                patch.dict(os.environ, {"VIBEVOICE_TOKENIZER_SOURCE": "modelscope"}, clear=False),
                patch.object(mod, "_download_modelscope_tokenizer", return_value=source_dir),
            ):
                mod.prefetch_tokenizer("Qwen/Qwen2.5-7B", model_dir=model_dir)

            self.assertEqual([str(source_dir)], calls)
            self.assertTrue((model_dir / "tokenizer.json").exists())

    def test_prefetch_tokenizer_auto_falls_back_to_huggingface(self) -> None:
        mod = _load_module()
        calls: list[str] = []

        class FakeTokenizer:
            def save_pretrained(self, output_dir: str) -> None:
                Path(output_dir, "tokenizer.json").write_text("{}", encoding="utf-8")

        class FakeAutoTokenizer:
            @staticmethod
            def from_pretrained(source: str):
                calls.append(source)
                return FakeTokenizer()

        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "model"
            model_dir.mkdir()
            fake_transformers = types.SimpleNamespace(AutoTokenizer=FakeAutoTokenizer)
            with (
                patch.dict(sys.modules, {"transformers": fake_transformers}),
                patch.dict(os.environ, {"VIBEVOICE_TOKENIZER_SOURCE": "auto"}, clear=False),
                patch.object(mod, "_download_modelscope_tokenizer", side_effect=RuntimeError("nope")),
            ):
                mod.prefetch_tokenizer("Qwen/Qwen2.5-7B", model_dir=model_dir)

            self.assertEqual(["Qwen/Qwen2.5-7B"], calls)
            self.assertTrue((model_dir / "tokenizer.json").exists())
