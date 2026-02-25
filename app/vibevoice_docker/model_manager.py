from __future__ import annotations

import gc
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import torch


ModelId = Literal["vibevoice-1.5b", "vibevoice-7b", "cosyvoice3-0.5b"]
BackendId = Literal["vibevoice", "cosyvoice3"]
logger = logging.getLogger("vibevoice_docker.model_manager")


@dataclass
class LoadedModel:
    model_id: ModelId
    backend: BackendId
    model_path: Path
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
        if model_id == "cosyvoice3-0.5b":
            return self._models_dir / "Fun-CosyVoice3-0.5B"
        raise ValueError(f"Unsupported model: {model_id}")

    def _pick_device(self) -> str:
        return "cuda" if torch.cuda.is_available() else "cpu"

    def _detect_backend(self, model_id: ModelId) -> BackendId:
        if model_id == "cosyvoice3-0.5b":
            return "cosyvoice3"
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

    def _load_cosyvoice3(
        self,
        model_path: Path,
        device: str,
        dtype: torch.dtype,
    ) -> tuple[Any, Any, int]:
        cosyvoice_root = Path("/opt/CosyVoice")
        matcha_root = cosyvoice_root / "third_party" / "Matcha-TTS"

        if cosyvoice_root.exists():
            cosyvoice_root_str = str(cosyvoice_root)
            if cosyvoice_root_str not in sys.path:
                sys.path.append(cosyvoice_root_str)

        if matcha_root.exists():
            matcha_root_str = str(matcha_root)
            if matcha_root_str not in sys.path:
                sys.path.append(matcha_root_str)

        try:
            from cosyvoice.cli.cosyvoice import AutoModel
        except Exception as exc:  # pragma: no cover - depends on image flavor
            raise RuntimeError("CosyVoice3 backend dependencies are unavailable in this image.") from exc

        fp16 = device == "cuda" and dtype in {torch.float16, torch.bfloat16}
        model = AutoModel(model_dir=str(model_path), fp16=fp16)
        self._ensure_cosyvoice3_cuda_provider(model, device=device)
        sample_rate = int(getattr(model, "sample_rate", 24000))
        return None, model, sample_rate

    def _ensure_cosyvoice3_cuda_provider(self, model: Any, device: str) -> None:
        if device != "cuda":
            return

        frontend = getattr(model, "frontend", None)
        if frontend is None:
            raise RuntimeError(
                "CosyVoice3 is running on CUDA but frontend is unavailable; refusing to fall back to CPU."
            )

        tokenizer_session = getattr(frontend, "speech_tokenizer_session", None)
        if tokenizer_session is None:
            raise RuntimeError(
                "CosyVoice3 is running on CUDA but speech tokenizer session is unavailable; refusing to fall back to CPU."
            )

        try:
            providers = list(tokenizer_session.get_providers())
        except Exception as exc:
            raise RuntimeError(
                "CosyVoice3 is running on CUDA but failed to query onnxruntime providers; refusing to fall back to CPU."
            ) from exc

        if "CUDAExecutionProvider" in providers:
            return

        raise RuntimeError(
            "CosyVoice3 detected CUDA but onnxruntime speech tokenizer is not using CUDAExecutionProvider "
            f"(providers={providers}); check onnxruntime-gpu CUDA dependencies, refusing to fall back to CPU."
        )

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

            backend = self._detect_backend(model_id)
            device = self._pick_device()
            dtype = torch.bfloat16 if device == "cuda" else torch.float32

            started_at = time.perf_counter()
            logger.info("Loading model %s from %s (backend=%s device=%s dtype=%s)", model_id, model_path, backend, device, dtype)

            if backend == "vibevoice":
                processor, model, sample_rate = self._load_vibevoice(model_path, device=device, dtype=dtype)
            else:
                processor, model, sample_rate = self._load_cosyvoice3(
                    model_path=model_path,
                    device=device,
                    dtype=dtype,
                )

            logger.info("Loaded model %s in %.1fs", model_id, time.perf_counter() - started_at)

            loaded = LoadedModel(
                model_id=model_id,
                backend=backend,
                model_path=model_path,
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
