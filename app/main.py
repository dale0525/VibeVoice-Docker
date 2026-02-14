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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from vibevoice_docker.audio_formats import AudioFormat, audio_to_wav_bytes, wav_bytes_to_mp3_bytes
from vibevoice_docker.cosyvoice_adapter import build_cosy_prompt_text, speaker_script_to_cosy_text
from vibevoice_docker.moss_adapter import build_moss_prompt_text, speaker_script_to_moss_text
from vibevoice_docker.model_manager import ModelId, ModelManager
from vibevoice_docker.settings import Settings
from vibevoice_docker.text_normalize import looks_like_speaker_script, normalize_single_speaker_script
from vibevoice_docker.torch_compat import (
    ensure_is_autocast_enabled_device_type_support,
    ensure_pad_sequence_padding_side_support,
)
from vibevoice_docker.voices import Voice, VoiceStore


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

app = FastAPI(title="TTS-Docker OpenAI-Compatible API", version="0.1.0")

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


class UpdateVoiceRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prompt_text: str | None = Field(None, description="Reference transcript for voice cloning")


@app.get("/", response_class=HTMLResponse)
def web_index() -> str:
    index_path = static_dir / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "<h1>TTS-Docker</h1><p>static/index.html not found</p>"


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
    if settings.model_id == "moss-ttsd-v1.0":
        owned_by = "openmoss"
    elif settings.model_id == "cosyvoice3-0.5b":
        owned_by = "funaudiollm"
    else:
        owned_by = "vibevoice"
    return {
        "object": "list",
        "data": [
            {"id": settings.model_id, "object": "model", "created": now, "owned_by": owned_by},
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
                "prompt_text": v.prompt_text,
            }
            for v in voices
        ],
    }


@app.post("/v1/voices")
async def create_voice(
    name: str = Form(...),
    file: UploadFile = File(...),
    prompt_text: str | None = Form(None),
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

    voice = voice_store.create_voice(name=name, sample_wav_path=wav_path, prompt_text=prompt_text)
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
        "prompt_text": voice.prompt_text,
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


@app.get("/v1/voices/{voice_id}/sample")
def get_voice_sample(voice_id: str, _: None = Depends(require_api_key)) -> Response:
    voice = voice_store.get_voice(voice_id)
    if voice is None:
        raise HTTPException(status_code=404, detail="voice not found")
    return FileResponse(path=str(voice.sample_path), media_type="audio/wav", filename=f"{voice.id}.wav")


@app.patch("/v1/voices/{voice_id}")
def update_voice(voice_id: str, payload: UpdateVoiceRequest, _: None = Depends(require_api_key)) -> dict[str, Any]:
    voice = voice_store.get_voice(voice_id)
    if voice is None:
        raise HTTPException(status_code=404, detail="voice not found")
    if voice.type == "builtin":
        raise HTTPException(status_code=400, detail="builtin voices cannot be edited")

    updated = voice_store.update_voice_prompt_text(voice_id=voice_id, prompt_text=payload.prompt_text)
    if updated is None:
        raise HTTPException(status_code=404, detail="voice not found")
    return {
        "id": updated.id,
        "object": "voice",
        "name": updated.name,
        "type": updated.type,
        "created": updated.created_at,
        "prompt_text": updated.prompt_text,
    }


_generation_lock = asyncio.Lock()
_active_user_requests = 0
_last_user_request_at = time.time()
_seen_user_request = False


def _request_process_exit() -> None:
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)


def _normalize_request_script(input_text: str) -> str:
    script = (input_text or "").strip()
    if not script:
        raise HTTPException(status_code=400, detail="input is required")

    if not looks_like_speaker_script(script):
        script = f"Speaker 0: {script}"

    try:
        return normalize_single_speaker_script(
            script,
            enable_cn_punct_normalize=settings.enable_cn_punct_normalize,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


async def _synthesize_with_voice(
    *,
    input_text: str,
    voice: Voice,
    response_format: AudioFormat,
    cfg_scale: float,
) -> Response:
    model_id = settings.model_id
    script = _normalize_request_script(input_text)

    request_started_at = time.perf_counter()
    logger.info(
        "TTS start model=%s voice=%s format=%s chars=%d",
        model_id,
        voice.id,
        response_format,
        len(input_text or ""),
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
            voice,
            float(cfg_scale),
        )
        inference_ms = (time.perf_counter() - inference_started_at) * 1000

    encode_started_at = time.perf_counter()
    wav_bytes = audio_to_wav_bytes(audio, sample_rate=sample_rate)
    if response_format == "mp3":
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


@app.post("/v1/audio/speech")
async def create_speech(payload: SpeechRequest, _: None = Depends(require_api_key)) -> Response:
    voice = voice_store.get_voice(payload.voice)
    if voice is None:
        return _openai_error(f"Unknown voice: {payload.voice}", code="voice_not_found", status_code=404)

    return await _synthesize_with_voice(
        input_text=payload.input,
        voice=voice,
        response_format=payload.response_format,
        cfg_scale=float(payload.vibevoice_cfg_scale),
    )


@app.post("/v1/audio/speech/reference")
async def create_speech_with_reference(
    input_text: str = Form(..., alias="input"),
    file: UploadFile = File(...),
    prompt_text: str | None = Form(None),
    response_format: AudioFormat = Form("wav"),
    vibevoice_cfg_scale: float = Form(3.0),
    _: None = Depends(require_api_key),
) -> Response:
    upload_dir = settings.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = Path(file.filename or "voice").name
    tmp_path = upload_dir / f"speech-ref-upload-{int(time.time())}-{safe_filename}"
    wav_path = upload_dir / f"speech-ref-converted-{tmp_path.stem}.wav"

    tmp_path.write_bytes(await file.read())
    _ffmpeg_to_wav_24k_mono(tmp_path, wav_path)

    reference_voice = Voice(
        id="reference-audio",
        name="reference-audio",
        type="custom",
        sample_path=wav_path,
        created_at=int(time.time()),
        prompt_text=(prompt_text or "").strip() or None,
    )
    try:
        return await _synthesize_with_voice(
            input_text=input_text,
            voice=reference_voice,
            response_format=response_format,
            cfg_scale=float(vibevoice_cfg_scale),
        )
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass


def _load_mono_wav(path: Path):
    import soundfile as sf
    import torch

    audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    wav = torch.from_numpy(audio).transpose(0, 1).contiguous()
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    return wav, int(sample_rate)


def _resample_audio_linear(wav, orig_sr: int, target_sr: int):
    if int(orig_sr) == int(target_sr):
        return wav

    import torch.nn.functional as F

    new_num_samples = int(round(wav.shape[-1] * float(target_sr) / float(orig_sr)))
    new_num_samples = max(1, new_num_samples)
    return F.interpolate(
        wav.unsqueeze(0),
        size=new_num_samples,
        mode="linear",
        align_corners=False,
    ).squeeze(0)


def _run_inference_vibevoice(loaded, script: str, voice: Voice, cfg_scale: float):
    import torch

    processor = loaded.processor
    model = loaded.model
    inputs = processor(
        text=[script],
        voice_samples=[[str(voice.sample_path)]],
        padding=True,
        return_tensors="pt",
        return_attention_mask=True,
    )

    target_device = loaded.device
    for k, v in list(inputs.items()):
        if torch.is_tensor(v):
            inputs[k] = v.to(target_device)

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
    return outputs.speech_outputs[0], loaded.sample_rate


def _decode_moss_audio(processor, outputs):
    import torch

    messages = processor.decode(outputs)
    if not messages or messages[0] is None:
        raise RuntimeError("No audio generated")

    wav_segments = []
    for wav in messages[0].audio_codes_list:
        if isinstance(wav, torch.Tensor):
            segment = wav.detach().to(dtype=torch.float32, device="cpu").reshape(-1)
        else:
            segment = torch.tensor(wav, dtype=torch.float32).reshape(-1)
        if segment.numel() > 0:
            wav_segments.append(segment)

    if not wav_segments:
        raise RuntimeError("No audio generated")
    return torch.cat(wav_segments, dim=0).numpy()


def _decode_cosyvoice_audio(outputs):
    import torch

    wav_segments = []
    for out in outputs:
        if not isinstance(out, dict):
            continue

        wav = out.get("tts_speech")
        if wav is None:
            continue

        if isinstance(wav, torch.Tensor):
            segment = wav.detach().to(dtype=torch.float32, device="cpu").reshape(-1)
        else:
            segment = torch.tensor(wav, dtype=torch.float32).reshape(-1)

        if segment.numel() > 0:
            wav_segments.append(segment)

    if not wav_segments:
        raise RuntimeError("No audio generated")
    return torch.cat(wav_segments, dim=0).numpy()


def _run_inference_moss_ttsd(loaded, script: str, voice: Voice):
    import torch

    ensure_is_autocast_enabled_device_type_support(torch_mod=torch)
    ensure_pad_sequence_padding_side_support(torch_mod=torch)

    processor = loaded.processor
    model = loaded.model
    sample_rate = int(loaded.sample_rate)

    moss_text = speaker_script_to_moss_text(script)
    prompt_text = build_moss_prompt_text(voice.prompt_text, moss_text)
    full_text = f"{prompt_text} {moss_text}".strip()

    wav, wav_sr = _load_mono_wav(voice.sample_path)
    wav = _resample_audio_linear(wav, wav_sr, sample_rate)

    reference_audio_codes = processor.encode_audios_from_wav([wav], sampling_rate=sample_rate)
    prompt_audio = processor.encode_audios_from_wav([wav], sampling_rate=sample_rate)[0]
    conversations = [
        [
            processor.build_user_message(text=full_text, reference=reference_audio_codes),
            processor.build_assistant_message(audio_codes_list=[prompt_audio]),
        ],
    ]

    batch = processor(conversations, mode="continuation")
    with torch.no_grad():
        outputs = model.generate(
            input_ids=batch["input_ids"].to(loaded.device),
            attention_mask=batch["attention_mask"].to(loaded.device),
            max_new_tokens=2000,
            audio_temperature=1.1,
            audio_top_p=0.9,
            audio_top_k=50,
            audio_repetition_penalty=1.1,
        )

    return _decode_moss_audio(processor, outputs), sample_rate


def _run_inference_cosyvoice3(loaded, script: str, voice: Voice):
    cosyvoice = loaded.model
    sample_rate = int(loaded.sample_rate)

    cosy_text = speaker_script_to_cosy_text(script)
    prompt_text = build_cosy_prompt_text(voice.prompt_text, cosy_text)
    outputs = cosyvoice.inference_zero_shot(
        cosy_text,
        prompt_text,
        str(voice.sample_path),
        stream=False,
        text_frontend=True,
    )
    return _decode_cosyvoice_audio(outputs), sample_rate


def _run_inference(model_id: ModelId, script: str, voice: Voice, cfg_scale: float):
    loaded = model_manager.get(model_id)
    if loaded.backend == "moss-ttsd":
        return _run_inference_moss_ttsd(loaded, script=script, voice=voice)
    if loaded.backend == "cosyvoice3":
        return _run_inference_cosyvoice3(loaded, script=script, voice=voice)
    return _run_inference_vibevoice(loaded, script=script, voice=voice, cfg_scale=cfg_scale)


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

            logger.info("Idle for %.0fs, exiting (EXIT_ON_IDLE_SECONDS=%s)", idle_seconds, settings.exit_on_idle_seconds)
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
                        voices[0],
                        3.0,
                    )
        except Exception:
            # 预热失败不影响服务启动
            pass

    asyncio.create_task(_maintenance_loop())
