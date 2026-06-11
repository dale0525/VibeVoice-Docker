"""
Prefetch tokenizer cache for VibeVoice models during image build.

Environment variables:
- MODELS_DIR: model root directory (default: /models)
- MODEL_ID: model selector (vibevoice-1.5b / vibevoice-7b / cosyvoice3-0.5b)
- VIBEVOICE_TOKENIZER_SOURCE: modelscope / huggingface / auto (default: modelscope)
- MODELSCOPE_TOKENIZER_CACHE: temporary ModelScope tokenizer cache
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional


def normalize_model_id(value: Optional[str]) -> str:
    if not value:
        return "vibevoice-1.5b"

    v = value.strip().lower()
    if v in {"vibevoice-1.5b", "1.5b", "vibevoice-1.5"}:
        return "vibevoice-1.5b"
    if v in {"vibevoice-7b", "7b", "vibevoice-7"}:
        return "vibevoice-7b"
    if v in {"cosyvoice3-0.5b", "cosyvoice3", "cosy3", "fun-cosyvoice3-0.5b"}:
        return "cosyvoice3-0.5b"
    raise ValueError(f"Unsupported MODEL_ID: {value!r}")


def is_vibevoice_model(model_id: str) -> bool:
    return model_id in {"vibevoice-1.5b", "vibevoice-7b"}


def resolve_vibevoice_model_dir_name(model_id: str) -> str:
    if model_id == "vibevoice-1.5b":
        return "VibeVoice-1.5B"
    if model_id == "vibevoice-7b":
        return "VibeVoice-7B"
    raise ValueError(f"Unsupported VibeVoice model_id: {model_id!r}")


def default_tokenizer_repo(model_id: str) -> str:
    if model_id == "vibevoice-1.5b":
        return "Qwen/Qwen2.5-1.5B"
    if model_id == "vibevoice-7b":
        return "Qwen/Qwen2.5-7B"
    raise ValueError(f"Unsupported VibeVoice model_id: {model_id!r}")


def read_preprocessor_tokenizer_repo(model_dir: Path) -> Optional[str]:
    config_path = model_dir / "preprocessor_config.json"
    if not config_path.exists():
        return None

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    repo = data.get("language_model_pretrained_name")
    if isinstance(repo, str) and repo.strip():
        return repo.strip()
    return None


def resolve_tokenizer_repo(model_id: str, model_dir: Path) -> str:
    return read_preprocessor_tokenizer_repo(model_dir) or default_tokenizer_repo(model_id)


def normalize_tokenizer_source(value: Optional[str]) -> str:
    if value is None:
        return "modelscope"

    v = value.strip().lower()
    if v in {"", "modelscope", "ms"}:
        return "modelscope"
    if v in {"hf", "huggingface", "hugging-face"}:
        return "huggingface"
    if v in {"auto", "fallback"}:
        return "auto"
    return "modelscope"


def _tokenizer_file_patterns() -> list[str]:
    return [
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "vocab.json",
        "merges.txt",
        "*.model",
        "*.tiktoken",
    ]


def _download_modelscope_tokenizer(repo_id: str, cache_dir: Optional[str]) -> Path:
    from modelscope.hub.snapshot_download import snapshot_download

    local_dir = Path(tempfile.mkdtemp(prefix="vibevoice-tokenizer-"))
    snapshot_download(
        model_id=repo_id,
        cache_dir=cache_dir,
        local_dir=str(local_dir),
        allow_file_pattern=_tokenizer_file_patterns(),
        max_workers=4,
    )
    return local_dir


def _resolve_modelscope_tokenizer_cache() -> tuple[Optional[str], bool]:
    configured = (os.getenv("MODELSCOPE_TOKENIZER_CACHE") or "").strip()
    if configured:
        return configured, False

    return tempfile.mkdtemp(prefix="vibevoice-tokenizer-cache-"), True


def prefetch_tokenizer(repo_id: str, model_dir: Path) -> None:
    from transformers import AutoTokenizer

    source = normalize_tokenizer_source(os.getenv("VIBEVOICE_TOKENIZER_SOURCE"))
    errors: list[str] = []

    if source in {"modelscope", "auto"}:
        local_dir: Path | None = None
        cache_dir, clean_cache = _resolve_modelscope_tokenizer_cache()
        try:
            local_dir = _download_modelscope_tokenizer(repo_id=repo_id, cache_dir=cache_dir)
            tokenizer = AutoTokenizer.from_pretrained(str(local_dir))
            tokenizer.save_pretrained(str(model_dir))
            print(f"[tokenizer-prefetch] saved tokenizer from ModelScope repo={repo_id} to {model_dir}")
            return
        except Exception as exc:
            errors.append(f"ModelScope tokenizer download failed: {exc}")
            if source == "modelscope":
                raise
        finally:
            if local_dir is not None:
                shutil.rmtree(local_dir, ignore_errors=True)
            if clean_cache and cache_dir:
                shutil.rmtree(cache_dir, ignore_errors=True)

    if source in {"huggingface", "auto"}:
        tokenizer = AutoTokenizer.from_pretrained(repo_id)
        tokenizer.save_pretrained(str(model_dir))
        print(f"[tokenizer-prefetch] saved tokenizer from Hugging Face repo={repo_id} to {model_dir}")
        return

    raise RuntimeError("; ".join(errors) or f"Unsupported tokenizer source: {source}")


def main() -> None:
    model_id = normalize_model_id(os.getenv("MODEL_ID"))
    if not is_vibevoice_model(model_id):
        print(f"[tokenizer-prefetch] skip MODEL_ID={model_id} (only VibeVoice requires prefetch)")
        return

    models_dir = Path(os.getenv("MODELS_DIR", "/models"))
    model_dir = models_dir / resolve_vibevoice_model_dir_name(model_id)
    tokenizer_repo = resolve_tokenizer_repo(model_id=model_id, model_dir=model_dir)

    print(
        f"[tokenizer-prefetch] MODEL_ID={model_id} model_dir={model_dir} "
        f"tokenizer_repo={tokenizer_repo}"
    )
    prefetch_tokenizer(tokenizer_repo, model_dir=model_dir)
    print(f"[tokenizer-prefetch] done repo={tokenizer_repo}")


if __name__ == "__main__":
    main()
