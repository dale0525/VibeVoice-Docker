ARG BASE_IMAGE=ghcr.io/dale0525/vibevoice-docker-base:1.5b
FROM ${BASE_IMAGE}

WORKDIR /opt

# 安装 VibeVoice 源码（直接使用仓库内置的 VibeVoice 目录）
RUN mkdir -p /opt/VibeVoice/demo
COPY VibeVoice/pyproject.toml VibeVoice/README.md VibeVoice/LICENSE /opt/VibeVoice/
COPY VibeVoice/vibevoice /opt/VibeVoice/vibevoice
COPY VibeVoice/demo/voices /opt/VibeVoice/demo/voices
RUN pip install --no-cache-dir --no-deps -e /opt/VibeVoice

# 复制服务端代码
COPY app /app
WORKDIR /app

ENV VIBEVOICE_DATA_DIR=/data
ENV VIBEVOICE_VOICES_DIR=/data/voices
ENV VIBEVOICE_BUILTIN_VOICES_DIR=/opt/VibeVoice/demo/voices

EXPOSE 8000 80
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1

