ARG BASE_IMAGE=ghcr.io/dale0525/tts-docker-base:1.5b
FROM ${BASE_IMAGE} AS app-common

WORKDIR /app

# 复制服务端代码
COPY app /app

ENV DATA_DIR=/data
ENV VOICES_DIR=/data/voices
ENV BUILTIN_VOICES_DIR=/data/voices_builtin

EXPOSE 8000 80
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1

FROM app-common AS app-vibevoice

WORKDIR /opt

# 仅 VibeVoice 模型镜像需要安装 VibeVoice Python 包
COPY VibeVoice/pyproject.toml VibeVoice/README.md VibeVoice/LICENSE /opt/VibeVoice/
COPY VibeVoice/vibevoice /opt/VibeVoice/vibevoice
RUN pip install --no-cache-dir --no-deps -e /opt/VibeVoice

WORKDIR /app

FROM app-common AS app
