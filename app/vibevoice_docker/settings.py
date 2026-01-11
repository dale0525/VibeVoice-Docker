from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


ModelId = Literal["vibevoice-1.5b", "vibevoice-7b"]


def _normalize_model_id(value: str | None, default: ModelId) -> ModelId:
    if value is None:
        return default
    v = value.strip().lower()
    if v in {"vibevoice-1.5b", "1.5b", "vibevoice-1.5"}:
        return "vibevoice-1.5b"
    if v in {"vibevoice-7b", "7b", "vibevoice-7"}:
        return "vibevoice-7b"
    return default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    voices_dir: Path
    builtin_voices_dir: Path
    models_dir: Path
    model_id: ModelId
    idle_unload_seconds: int
    exit_on_idle_seconds: int
    max_loaded_models: int
    preload_on_startup: bool
    warmup_on_preload: bool
    enable_cn_punct_normalize: bool
    api_key: str | None

    @staticmethod
    def load() -> "Settings":
        import os

        data_dir = Path(os.environ.get("VIBEVOICE_DATA_DIR", "/data")).resolve()
        voices_dir = Path(os.environ.get("VIBEVOICE_VOICES_DIR", str(data_dir / "voices"))).resolve()

        builtin_override = os.environ.get("VIBEVOICE_BUILTIN_VOICES_DIR")
        if builtin_override:
            builtin_voices_dir = Path(builtin_override).resolve()
        else:
            repo_root_guess = Path(__file__).resolve().parents[2]
            candidates = [
                repo_root_guess / "VibeVoice" / "demo" / "voices",
                Path("/opt/VibeVoice/demo/voices"),
                data_dir / "voices_builtin",
            ]
            builtin_voices_dir = next((p.resolve() for p in candidates if p.exists()), candidates[-1].resolve())

        models_dir = Path(os.environ.get("VIBEVOICE_MODELS_DIR", "/models")).resolve()
        model_id = _normalize_model_id(
            os.environ.get("VIBEVOICE_MODEL_ID") or os.environ.get("VIBEVOICE_PRELOAD_MODEL"),
            "vibevoice-1.5b",
        )

        idle_unload_seconds = _env_int(os.environ.get("VIBEVOICE_IDLE_UNLOAD_SECONDS"), 15 * 60)
        exit_on_idle_seconds = max(0, _env_int(os.environ.get("VIBEVOICE_EXIT_ON_IDLE_SECONDS"), 0))
        max_loaded_models = max(1, _env_int(os.environ.get("VIBEVOICE_MAX_LOADED_MODELS"), 1))
        preload_on_startup = bool((os.environ.get("VIBEVOICE_PRELOAD_MODEL") or "").strip())
        warmup_on_preload = _env_bool(os.environ.get("VIBEVOICE_WARMUP_ON_PRELOAD"), True)
        enable_cn_punct_normalize = _env_bool(
            os.environ.get("VIBEVOICE_ENABLE_CN_PUNCT_NORMALIZE"),
            True,
        )
        api_key = os.environ.get("VIBEVOICE_API_KEY") or None

        return Settings(
            data_dir=data_dir,
            voices_dir=voices_dir,
            builtin_voices_dir=builtin_voices_dir,
            models_dir=models_dir,
            model_id=model_id,
            idle_unload_seconds=idle_unload_seconds,
            exit_on_idle_seconds=exit_on_idle_seconds,
            max_loaded_models=max_loaded_models,
            preload_on_startup=preload_on_startup,
            warmup_on_preload=warmup_on_preload,
            enable_cn_punct_normalize=enable_cn_punct_normalize,
            api_key=api_key,
        )
