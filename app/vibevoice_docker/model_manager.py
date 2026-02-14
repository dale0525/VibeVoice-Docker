from __future__ import annotations

import gc
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import torch


ModelId = Literal["vibevoice-1.5b", "vibevoice-7b", "moss-ttsd-v1.0"]
BackendId = Literal["vibevoice", "moss-ttsd"]
logger = logging.getLogger("vibevoice_docker.model_manager")


@dataclass
class LoadedModel:
    model_id: ModelId
    backend: BackendId
    model_path: Path
    codec_path: Path | None
    device: str
    sample_rate: int
    processor: Any
    model: Any
    last_used_at: float


class ModelManager:
    def __init__(self, models_dir: Path, idle_unload_seconds: int, max_loaded_models: int = 1):
        self._models_dir = models_dir
        self._idle_unload_seconds = idle_unload_seconds
        self._max_loaded_models = max(1, int(max_loaded_models))
        self._lock = Lock()
        self._loaded: dict[ModelId, LoadedModel] = {}

    def resolve_model_path(self, model_id: ModelId) -> Path:
        if model_id == "vibevoice-1.5b":
            return self._models_dir / "VibeVoice-1.5B"
        if model_id == "vibevoice-7b":
            return self._models_dir / "VibeVoice-7B"
        if model_id == "moss-ttsd-v1.0":
            return self._models_dir / "MOSS-TTSD-v1.0"
        raise ValueError(f"Unsupported model: {model_id}")

    def resolve_codec_path(self, model_id: ModelId) -> Path | None:
        if model_id == "moss-ttsd-v1.0":
            return self._models_dir / "MOSS-Audio-Tokenizer"
        return None

    def _pick_device(self) -> str:
        return "cuda" if torch.cuda.is_available() else "cpu"

    def _detect_backend(self, model_id: ModelId) -> BackendId:
        if model_id == "moss-ttsd-v1.0":
            return "moss-ttsd"
        return "vibevoice"

    def _load_vibevoice(self, model_path: Path, device: str, dtype: torch.dtype) -> tuple[Any, Any, int]:
        try:
            from vibevoice.modular.modeling_vibevoice_inference import VibeVoiceForConditionalGenerationInference
            from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor
        except Exception as exc:  # pragma: no cover - depends on image flavor
            raise RuntimeError("VibeVoice backend dependencies are unavailable in this image.") from exc

        processor = VibeVoiceProcessor.from_pretrained(str(model_path))
        model = VibeVoiceForConditionalGenerationInference.from_pretrained(
            str(model_path),
            torch_dtype=dtype,
            device_map=device,
            attn_implementation="sdpa",
        )
        model.eval()
        model.set_ddpm_inference_steps(num_steps=10)
        return processor, model, 24000

    def _load_moss_ttsd(
        self,
        model_path: Path,
        codec_path: Path,
        device: str,
        dtype: torch.dtype,
    ) -> tuple[Any, Any, int]:
        try:
            from transformers import AutoModel, AutoProcessor
        except Exception as exc:  # pragma: no cover - depends on image flavor
            raise RuntimeError("MOSS-TTSD backend requires transformers>=5 with trust_remote_code support.") from exc

        processor = AutoProcessor.from_pretrained(
            str(model_path),
            trust_remote_code=True,
            codec_path=str(codec_path),
        )
        if getattr(processor, "audio_tokenizer", None) is not None:
            processor.audio_tokenizer = processor.audio_tokenizer.to(device)
            processor.audio_tokenizer.eval()

        def _load_with_attn(attn_implementation: str):
            return AutoModel.from_pretrained(
                str(model_path),
                trust_remote_code=True,
                attn_implementation=attn_implementation,
                torch_dtype=dtype,
            ).to(device)

        if device == "cuda":
            try:
                model = _load_with_attn("flash_attention_2")
            except Exception:
                model = _load_with_attn("sdpa")
        else:
            model = _load_with_attn("sdpa")

        model.eval()
        sample_rate = int(getattr(processor.model_config, "sampling_rate", 24000))
        return processor, model, sample_rate

    def get(self, model_id: ModelId) -> LoadedModel:
        with self._lock:
            loaded = self._loaded.get(model_id)
            if loaded is not None:
                loaded.last_used_at = time.time()
                return loaded

            while len(self._loaded) >= self._max_loaded_models:
                lru_id, lru_model = min(self._loaded.items(), key=lambda kv: kv[1].last_used_at)
                self._unload_locked(lru_id, lru_model)

            model_path = self.resolve_model_path(model_id)
            if not model_path.exists():
                raise FileNotFoundError(
                    f"模型未找到：{model_path}。请确认镜像构建时已下载模型，或挂载了正确的模型目录。"
                )

            codec_path = self.resolve_codec_path(model_id)
            if codec_path is not None and not codec_path.exists():
                raise FileNotFoundError(f"Codec 模型未找到：{codec_path}")

            backend = self._detect_backend(model_id)
            device = self._pick_device()
            dtype = torch.bfloat16 if device == "cuda" else torch.float32

            started_at = time.perf_counter()
            logger.info("Loading model %s from %s (backend=%s device=%s dtype=%s)", model_id, model_path, backend, device, dtype)

            if backend == "vibevoice":
                processor, model, sample_rate = self._load_vibevoice(model_path, device=device, dtype=dtype)
            else:
                assert codec_path is not None
                processor, model, sample_rate = self._load_moss_ttsd(
                    model_path=model_path,
                    codec_path=codec_path,
                    device=device,
                    dtype=dtype,
                )

            logger.info("Loaded model %s in %.1fs", model_id, time.perf_counter() - started_at)

            loaded = LoadedModel(
                model_id=model_id,
                backend=backend,
                model_path=model_path,
                codec_path=codec_path,
                device=device,
                sample_rate=sample_rate,
                processor=processor,
                model=model,
                last_used_at=time.time(),
            )
            self._loaded[model_id] = loaded
            return loaded

    def _unload_locked(self, model_id: ModelId, loaded: LoadedModel) -> None:
        try:
            logger.info("Unloading model %s", model_id)
            self._loaded.pop(model_id, None)
            try:
                del loaded.model
            except Exception:
                pass
            try:
                del loaded.processor
            except Exception:
                pass
        finally:
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def maybe_unload_idle(self) -> list[ModelId]:
        now = time.time()
        unloaded: list[ModelId] = []
        with self._lock:
            for model_id, loaded in list(self._loaded.items()):
                if now - loaded.last_used_at < self._idle_unload_seconds:
                    continue
                self._unload_locked(model_id, loaded)
                unloaded.append(model_id)

        return unloaded
