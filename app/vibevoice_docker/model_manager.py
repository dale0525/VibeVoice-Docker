from __future__ import annotations

import gc
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Literal

import torch

from vibevoice.modular.modeling_vibevoice_inference import VibeVoiceForConditionalGenerationInference
from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor


ModelId = Literal["vibevoice-1.5b", "vibevoice-7b"]
logger = logging.getLogger("vibevoice_docker.model_manager")


@dataclass
class LoadedModel:
    model_id: ModelId
    model_path: Path
    device: str
    processor: VibeVoiceProcessor
    model: VibeVoiceForConditionalGenerationInference
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
        raise ValueError(f"Unsupported model: {model_id}")

    def _pick_device(self) -> str:
        return "cuda" if torch.cuda.is_available() else "cpu"

    def get(self, model_id: ModelId) -> LoadedModel:
        with self._lock:
            loaded = self._loaded.get(model_id)
            if loaded is not None:
                loaded.last_used_at = time.time()
                return loaded

            # 仅保留有限数量的已加载模型，避免显存/内存被占满
            while len(self._loaded) >= self._max_loaded_models:
                lru_id, lru_model = min(self._loaded.items(), key=lambda kv: kv[1].last_used_at)
                self._unload_locked(lru_id, lru_model)

            model_path = self.resolve_model_path(model_id)
            if not model_path.exists():
                raise FileNotFoundError(
                    f"模型未找到：{model_path}。请确认镜像构建时已下载模型，或挂载了正确的模型目录。"
                )

            device = self._pick_device()
            dtype = torch.bfloat16 if device == "cuda" else torch.float32

            started_at = time.perf_counter()
            logger.info("Loading model %s from %s (device=%s dtype=%s)", model_id, model_path, device, dtype)
            processor = VibeVoiceProcessor.from_pretrained(str(model_path))
            model = VibeVoiceForConditionalGenerationInference.from_pretrained(
                str(model_path),
                torch_dtype=dtype,
                device_map=device,
                attn_implementation="sdpa",
            )
            model.eval()
            model.set_ddpm_inference_steps(num_steps=10)
            logger.info("Loaded model %s in %.1fs", model_id, time.perf_counter() - started_at)

            loaded = LoadedModel(
                model_id=model_id,
                model_path=model_path,
                device=device,
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
