from __future__ import annotations

import io
import subprocess
from typing import Literal

import numpy as np


AudioFormat = Literal["wav", "mp3"]


def audio_to_wav_bytes(audio: "np.ndarray | object", sample_rate: int) -> bytes:
    try:
        import torch
    except Exception:  # pragma: no cover
        torch = None  # type: ignore

    if torch is not None and isinstance(audio, torch.Tensor):
        audio_np = audio.detach().cpu().float().numpy()
    else:
        audio_np = np.asarray(audio, dtype=np.float32)

    audio_np = np.squeeze(audio_np)
    audio_np = np.clip(audio_np, -1.0, 1.0)

    try:
        import soundfile as sf
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("缺少依赖：soundfile（用于写出 WAV）") from exc

    buf = io.BytesIO()
    sf.write(buf, audio_np, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def wav_bytes_to_mp3_bytes(wav_bytes: bytes, bitrate: str = "192k") -> bytes:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "mp3",
            "-b:a",
            bitrate,
            "pipe:1",
        ],
        input=wav_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 转码失败: {proc.stderr.decode('utf-8', errors='ignore')}")
    return proc.stdout

