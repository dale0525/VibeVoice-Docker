from __future__ import annotations

import asyncio
import io
import logging
import os
import signal
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from vibevoice_docker.audio_formats import AudioFormat, audio_to_wav_bytes, wav_bytes_to_mp3_bytes
from vibevoice_docker.model_manager import ModelId, ModelManager
from vibevoice_docker.settings import Settings
from vibevoice_docker.text_normalize import looks_like_speaker_script, normalize_single_speaker_script
from vibevoice_docker.voices import VoiceStore


if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

logger = logging.getLogger("vibevoice_docker")

settings = Settings.load()
voice_store = VoiceStore(builtin_dir=settings.builtin_voices_dir, custom_dir=settings.voices_dir)
model_manager = ModelManager(
    models_dir=settings.models_dir,
    idle_unload_seconds=settings.idle_unload_seconds,
    max_loaded_models=settings.max_loaded_models,
)

app = FastAPI(title="VibeVoice OpenAI-Compatible API", version="0.1.0")

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.middleware("http")
async def _log_http_requests(request: Request, call_next):
    global _active_user_requests
    global _last_user_request_at
    global _seen_user_request

    started_at = time.perf_counter()
    track_for_idle = request.url.path not in {"/healthz", "/ping"}
    if track_for_idle:
        _seen_user_request = True
        _active_user_requests += 1
        _last_user_request_at = time.time()

    try:
        response = await call_next(request)
    finally:
        if track_for_idle:
            _active_user_requests = max(0, _active_user_requests - 1)
            _last_user_request_at = time.time()

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    if request.url.path.startswith("/v1/") or request.url.path in {"/healthz", "/ping"}:
        logger.info("%s %s -> %s (%.0fms)", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


def _openai_error(message: str, code: str = "bad_request", status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "param": None,
                "code": code,
            }
        },
    )


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if request.url.path.startswith("/v1/"):
        return _openai_error(str(exc.detail), code="http_error", status_code=exc.status_code)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    if request.url.path.startswith("/v1/"):
        return _openai_error("Request validation failed", code="validation_error", status_code=422)
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s %s", request.method, request.url.path)
    if request.url.path.startswith("/v1/"):
        return _openai_error("Internal server error", code="internal_error", status_code=500)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def require_api_key(request: Request) -> None:
    if not settings.api_key:
        return
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = auth.split(" ", 1)[1].strip()
    if token != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str | None = Field(None, description="兼容字段：会被忽略（镜像已固定模型）")
    input: str = Field(..., description="Text to speak (plain text or single-speaker Speaker script)")
    voice: str = Field(..., description="Voice id from /v1/voices")
    response_format: AudioFormat = Field("wav", description="wav | mp3")
    vibevoice_cfg_scale: float = Field(3.0, description="CFG scale (advanced)")


@app.get("/", response_class=HTMLResponse)
def web_index() -> str:
    index_path = static_dir / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "<h1>VibeVoice-Docker</h1><p>static/index.html not found</p>"


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {
        "status": "ok",
        "time": int(time.time()),
        "cuda_available": _cuda_available(),
    }


@app.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "healthy"}


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


@app.get("/v1/models")
def list_models(_: None = Depends(require_api_key)) -> dict[str, Any]:
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {"id": settings.model_id, "object": "model", "created": now, "owned_by": "vibevoice"},
        ],
    }


@app.get("/v1/voices")
def list_voices(_: None = Depends(require_api_key)) -> dict[str, Any]:
    voice_store.ensure_dirs()
    voices = voice_store.list_voices()
    return {
        "object": "list",
        "data": [
            {
                "id": v.id,
                "object": "voice",
                "name": v.name,
                "type": v.type,
                "created": v.created_at,
            }
            for v in voices
        ],
    }


@app.post("/v1/voices")
async def create_voice(
    name: str = Form(...),
    file: UploadFile = File(...),
    _: None = Depends(require_api_key),
) -> dict[str, Any]:
    voice_store.ensure_dirs()

    if not name.strip():
        raise HTTPException(status_code=400, detail="name is required")

    upload_dir = settings.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = Path(file.filename or "voice").name
    tmp_path = upload_dir / f"upload-{int(time.time())}-{safe_filename}"
    tmp_path.write_bytes(await file.read())

    # 统一转换为 24kHz mono wav，便于稳定复用
    wav_path = upload_dir / f"converted-{tmp_path.stem}.wav"
    _ffmpeg_to_wav_24k_mono(tmp_path, wav_path)

    voice = voice_store.create_voice(name=name, sample_wav_path=wav_path)
    try:
        tmp_path.unlink(missing_ok=True)
        wav_path.unlink(missing_ok=True)
    except Exception:
        pass
    return {
        "id": voice.id,
        "object": "voice",
        "name": voice.name,
        "type": voice.type,
        "created": voice.created_at,
    }


def _ffmpeg_to_wav_24k_mono(src: Path, dst: Path) -> None:
    import subprocess

    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(src),
            "-ac",
            "1",
            "-ar",
            "24000",
            str(dst),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise HTTPException(
            status_code=400,
            detail=f"音频转换失败: {proc.stderr.decode('utf-8', errors='ignore')}",
        )


@app.delete("/v1/voices/{voice_id}")
def delete_voice(voice_id: str, _: None = Depends(require_api_key)) -> dict[str, Any]:
    voice = voice_store.get_voice(voice_id)
    if voice is None:
        raise HTTPException(status_code=404, detail="voice not found")
    if voice.type == "builtin":
        raise HTTPException(status_code=400, detail="builtin voices cannot be deleted")
    ok = voice_store.delete_voice(voice_id)
    return {"deleted": ok, "id": voice_id, "object": "voice"}


_generation_lock = asyncio.Lock()
_active_user_requests = 0
_last_user_request_at = time.time()
_seen_user_request = False


def _request_process_exit() -> None:
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)


@app.post("/v1/audio/speech")
async def create_speech(payload: SpeechRequest, _: None = Depends(require_api_key)) -> Response:
    model_id = settings.model_id
    voice = voice_store.get_voice(payload.voice)
    if voice is None:
        return _openai_error(f"Unknown voice: {payload.voice}", code="voice_not_found", status_code=404)

    script = payload.input.strip()
    if not looks_like_speaker_script(script):
        script = f"Speaker 0: {script}"
    try:
        script = normalize_single_speaker_script(
            script,
            enable_cn_punct_normalize=settings.enable_cn_punct_normalize,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    request_started_at = time.perf_counter()
    logger.info(
        "TTS start model=%s voice=%s format=%s chars=%d",
        model_id,
        voice.id,
        payload.response_format,
        len(payload.input or ""),
    )

    lock_wait_started_at = time.perf_counter()
    async with _generation_lock:
        lock_wait_ms = (time.perf_counter() - lock_wait_started_at) * 1000
        if lock_wait_ms >= 50:
            logger.info("TTS waited for lock %.0fms", lock_wait_ms)

        inference_started_at = time.perf_counter()
        audio, sample_rate = await asyncio.to_thread(
            _run_inference,
            model_id,
            script,
            voice.sample_path,
            float(payload.vibevoice_cfg_scale),
        )
        inference_ms = (time.perf_counter() - inference_started_at) * 1000

    encode_started_at = time.perf_counter()
    wav_bytes = audio_to_wav_bytes(audio, sample_rate=sample_rate)
    if payload.response_format == "mp3":
        mp3_bytes = wav_bytes_to_mp3_bytes(wav_bytes)
        total_ms = (time.perf_counter() - request_started_at) * 1000
        encode_ms = (time.perf_counter() - encode_started_at) * 1000
        logger.info(
            "TTS done model=%s voice=%s sr=%s bytes=%d total=%.0fms (infer=%.0fms encode=%.0fms)",
            model_id,
            voice.id,
            sample_rate,
            len(mp3_bytes),
            total_ms,
            inference_ms,
            encode_ms,
        )
        return StreamingResponse(io.BytesIO(mp3_bytes), media_type="audio/mpeg")

    total_ms = (time.perf_counter() - request_started_at) * 1000
    encode_ms = (time.perf_counter() - encode_started_at) * 1000
    logger.info(
        "TTS done model=%s voice=%s sr=%s bytes=%d total=%.0fms (infer=%.0fms encode=%.0fms)",
        model_id,
        voice.id,
        sample_rate,
        len(wav_bytes),
        total_ms,
        inference_ms,
        encode_ms,
    )
    return StreamingResponse(io.BytesIO(wav_bytes), media_type="audio/wav")

def _run_inference(model_id: ModelId, script: str, voice_sample_path: Path, cfg_scale: float):
    loaded = model_manager.get(model_id)
    processor = loaded.processor
    model = loaded.model

    inputs = processor(
        text=[script],
        voice_samples=[[str(voice_sample_path)]],
        padding=True,
        return_tensors="pt",
        return_attention_mask=True,
    )

    target_device = loaded.device
    for k, v in list(inputs.items()):
        try:
            import torch

            if torch.is_tensor(v):
                inputs[k] = v.to(target_device)
        except Exception:
            pass

    outputs = model.generate(
        **inputs,
        max_new_tokens=None,
        cfg_scale=cfg_scale,
        tokenizer=processor.tokenizer,
        generation_config={"do_sample": False},
        show_progress_bar=False,
        refresh_negative=True,
        verbose=False,
        is_prefill=True,
    )

    if not outputs.speech_outputs or outputs.speech_outputs[0] is None:
        raise RuntimeError("No audio generated")
    return outputs.speech_outputs[0], 24000


@app.on_event("startup")
async def _startup() -> None:
    voice_store.ensure_dirs()

    async def _maintenance_loop() -> None:
        last_unload_checked_at = 0.0
        while True:
            await asyncio.sleep(1)
            now = time.time()

            if now - last_unload_checked_at >= 30:
                last_unload_checked_at = now
                try:
                    model_manager.maybe_unload_idle()
                except Exception:
                    pass

            if settings.exit_on_idle_seconds <= 0:
                continue

            if not _seen_user_request:
                continue

            if _active_user_requests > 0:
                continue

            idle_seconds = now - _last_user_request_at
            if idle_seconds < settings.exit_on_idle_seconds:
                continue

            logger.info("Idle for %.0fs, exiting (VIBEVOICE_EXIT_ON_IDLE_SECONDS=%s)", idle_seconds, settings.exit_on_idle_seconds)
            _request_process_exit()
            return

    if settings.preload_on_startup:
        try:
            model_id = settings.model_id
            await asyncio.to_thread(model_manager.get, model_id)
            if settings.warmup_on_preload:
                voices = voice_store.list_voices()
                if voices:
                    await asyncio.to_thread(
                        _run_inference,
                        model_id,
                        "Speaker 0: Hello.",
                        voices[0].sample_path,
                        3.0,
                    )
        except Exception:
            # 预热失败不影响服务启动
            pass

    asyncio.create_task(_maintenance_loop())
