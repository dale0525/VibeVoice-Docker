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


def _env_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


ModelId = Literal["vibevoice-1.5b", "vibevoice-7b", "cosyvoice3-0.5b"]
InferenceAccelerator = Literal["auto", "cpu", "cuda", "mps"]


def _normalize_model_id(value: str | None, default: ModelId) -> ModelId:
    if value is None:
        return default
    v = value.strip().lower()
    if v in {"vibevoice-1.5b", "1.5b", "vibevoice-1.5"}:
        return "vibevoice-1.5b"
    if v in {"vibevoice-7b", "7b", "vibevoice-7"}:
        return "vibevoice-7b"
    if v in {"cosyvoice3-0.5b", "cosyvoice3", "cosy3", "fun-cosyvoice3-0.5b"}:
        return "cosyvoice3-0.5b"
    return default


def _normalize_accelerator(value: str | None, default: InferenceAccelerator) -> InferenceAccelerator:
    if value is None:
        return default
    v = value.strip().lower()
    if v in {"", "auto", "default"}:
        return "auto"
    if v in {"cpu", "none", "off", "false", "0"}:
        return "cpu"
    if v in {"cuda", "gpu", "nvidia"}:
        return "cuda"
    if v in {"mps", "metal", "apple", "apple-silicon", "apple_silicon"}:
        return "mps"
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
    vibevoice_default_seed: int
    vibevoice_default_temperature: float
    inference_accelerator: InferenceAccelerator
    cosyvoice3_load_trt: bool
    cosyvoice3_load_vllm: bool
    api_key: str | None

    @staticmethod
    def load() -> "Settings":
        import os

        data_dir = Path(os.environ.get("DATA_DIR", "/data")).resolve()
        voices_dir = Path(os.environ.get("VOICES_DIR", str(data_dir / "voices"))).resolve()

        builtin_override = os.environ.get("BUILTIN_VOICES_DIR")
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

        models_dir = Path(os.environ.get("MODELS_DIR", "/models")).resolve()
        model_id = _normalize_model_id(
            os.environ.get("MODEL_ID") or os.environ.get("MODEL"),
            "vibevoice-1.5b",
        )

        idle_unload_seconds = _env_int(os.environ.get("IDLE_UNLOAD_SECONDS"), 15 * 60)
        exit_on_idle_seconds = max(0, _env_int(os.environ.get("EXIT_ON_IDLE_SECONDS"), 0))
        max_loaded_models = max(1, _env_int(os.environ.get("MAX_LOADED_MODELS"), 1))
        preload_on_startup = bool((os.environ.get("PRELOAD_MODEL") or "").strip())
        warmup_on_preload = _env_bool(os.environ.get("WARMUP_ON_PRELOAD"), True)
        enable_cn_punct_normalize = _env_bool(
            os.environ.get("ENABLE_CN_PUNCT_NORMALIZE"),
            True,
        )
        vibevoice_default_seed = max(0, _env_int(os.environ.get("VIBEVOICE_DEFAULT_SEED"), 42))
        vibevoice_default_temperature = _env_float(os.environ.get("VIBEVOICE_DEFAULT_TEMPERATURE"), 0.0)
        vibevoice_default_temperature = min(2.0, max(0.0, vibevoice_default_temperature))
        inference_accelerator = _normalize_accelerator(
            os.environ.get("TTS_ACCELERATOR") or os.environ.get("INFERENCE_ACCELERATOR"),
            "auto",
        )
        cosyvoice3_load_trt = _env_bool(os.environ.get("COSYVOICE3_LOAD_TRT"), False)
        cosyvoice3_load_vllm = _env_bool(os.environ.get("COSYVOICE3_LOAD_VLLM"), False)
        api_key = os.environ.get("API_KEY") or None

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
            vibevoice_default_seed=vibevoice_default_seed,
            vibevoice_default_temperature=vibevoice_default_temperature,
            inference_accelerator=inference_accelerator,
            cosyvoice3_load_trt=cosyvoice3_load_trt,
            cosyvoice3_load_vllm=cosyvoice3_load_vllm,
            api_key=api_key,
        )
