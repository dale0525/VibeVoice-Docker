FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime

# 构建参数：默认使用国内镜像源（可在 docker build 时通过 --build-arg 覆盖）
ARG USE_CN_MIRRORS=1
ARG APT_MIRROR_HOST=mirrors.aliyun.com
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    if [ "${USE_CN_MIRRORS}" = "1" ]; then \
        for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do \
            [ -f "$f" ] || continue; \
            sed -i \
                -e "s@archive.ubuntu.com@${APT_MIRROR_HOST}@g" \
                -e "s@security.ubuntu.com@${APT_MIRROR_HOST}@g" \
                -e "s@deb.debian.org@${APT_MIRROR_HOST}@g" \
                -e "s@security.debian.org@${APT_MIRROR_HOST}@g" \
                "$f"; \
        done; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        ca-certificates; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt

# 先安装最小依赖，确保后续下载模型步骤可缓存
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 在镜像构建阶段下载模型（尽量靠前，避免调试改代码时反复下载）
ARG VIBEVOICE_MODEL_ID=vibevoice-1.5b
ENV VIBEVOICE_MODEL_ID=${VIBEVOICE_MODEL_ID}
ENV VIBEVOICE_MODELS_DIR=/models
ENV MODELSCOPE_CACHE=/models/modelscope-cache
COPY scripts/download_models.py /opt/scripts/download_models.py
RUN python /opt/scripts/download_models.py

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
