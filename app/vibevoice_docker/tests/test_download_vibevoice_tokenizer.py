import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


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
