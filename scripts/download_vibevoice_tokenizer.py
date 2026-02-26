"""
Prefetch tokenizer cache for VibeVoice models during image build.

Environment variables:
- MODELS_DIR: model root directory (default: /models)
- MODEL_ID: model selector (vibevoice-1.5b / vibevoice-7b / cosyvoice3-0.5b)
"""

from __future__ import annotations

import json
import os
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


def prefetch_tokenizer(repo_id: str) -> None:
    from transformers import AutoTokenizer

    # Build-time prefetch to HuggingFace cache. Runtime uses local_files_only=True.
    AutoTokenizer.from_pretrained(repo_id)


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
    prefetch_tokenizer(tokenizer_repo)
    print(f"[tokenizer-prefetch] done repo={tokenizer_repo}")


if __name__ == "__main__":
    main()
