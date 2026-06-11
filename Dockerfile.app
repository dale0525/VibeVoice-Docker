ARG BASE_IMAGE=ghcr.io/dale0525/tts-docker-base:1.5b
FROM ${BASE_IMAGE} AS app-common

WORKDIR /app

# 复制服务端代码
COPY app /app

ENV DATA_DIR=/data
ENV VOICES_DIR=/data/voices
ENV BUILTIN_VOICES_DIR=/data/voices_builtin
ENV HF_HOME=/models/hf-cache
ENV HUGGINGFACE_HUB_CACHE=/models/hf-cache/hub
ENV TRANSFORMERS_CACHE=/models/hf-cache/transformers
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1
ENV HF_HUB_DISABLE_TELEMETRY=1

EXPOSE 8000 80
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1

# model-block:start:vibevoice-1.5b
# model-block:start:vibevoice-7b
FROM app-common AS app-vibevoice

WORKDIR /opt

# 仅 VibeVoice 模型镜像需要安装 VibeVoice Python 包
COPY VibeVoice/pyproject.toml VibeVoice/README.md VibeVoice/LICENSE /opt/VibeVoice/
COPY VibeVoice/vibevoice /opt/VibeVoice/vibevoice
RUN pip install --no-cache-dir --no-deps -e /opt/VibeVoice
COPY scripts/download_vibevoice_tokenizer.py /opt/scripts/download_vibevoice_tokenizer.py
RUN python /opt/scripts/download_vibevoice_tokenizer.py

WORKDIR /app
# model-block:end:vibevoice-7b
# model-block:end:vibevoice-1.5b

FROM app-common AS app
