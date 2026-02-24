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
ARG MODEL_ID=vibevoice-1.5b
COPY requirements.txt /tmp/requirements.txt
RUN set -eux; \
    if [ "${MODEL_ID}" = "cosyvoice3-0.5b" ]; then \
        apt-get update; \
        apt-get install -y --no-install-recommends g++; \
        rm -rf /var/lib/apt/lists/*; \
    fi; \
    pip install --no-cache-dir -r /tmp/requirements.txt; \
    if [ "${MODEL_ID}" = "moss-ttsd-v1.0" ]; then \
        pip install --no-cache-dir \
            "transformers==5.0.0" \
            "safetensors==0.6.2" \
            "soundfile==0.13.1" \
            "torchaudio==2.3.1" \
            "tiktoken==0.12.0" \
            "einops==0.8.1"; \
    elif [ "${MODEL_ID}" = "cosyvoice3-0.5b" ]; then \
        pip install --no-cache-dir \
            "conformer==0.3.2" \
            "diffusers==0.29.0" \
            "gdown==5.1.0" \
            "hydra-core==1.3.2" \
            "hyperpyyaml==1.2.3" \
            "inflect==7.3.1" \
            "librosa==0.10.2" \
            "lightning==2.2.4" \
            "matplotlib==3.7.5" \
            "numpy==1.26.4" \
            "omegaconf==2.3.0" \
            "onnx==1.16.0" \
            "onnxruntime-gpu==1.18.0" \
            "pyarrow==18.1.0" \
            "pyworld==0.3.4" \
            "tiktoken==0.12.0" \
            "rich==13.7.1" \
            "torchaudio==2.3.1" \
            "transformers==4.51.3" \
            "wetext==0.0.4" \
            "wget==3.2" \
            "x-transformers==2.11.24"; \
        pip install --no-cache-dir --no-build-isolation \
            "openai-whisper==20231117"; \
    fi

# 在镜像构建阶段下载模型（尽量靠前，避免调试改代码时反复下载）
ENV MODEL_ID=${MODEL_ID}
ENV MODELS_DIR=/models
ENV MODELSCOPE_CACHE=/models/modelscope-cache
COPY scripts/download_models.py /opt/scripts/download_models.py
RUN python /opt/scripts/download_models.py

RUN set -eux; \
    if [ "${MODEL_ID}" = "cosyvoice3-0.5b" ]; then \
        apt-get update; \
        apt-get install -y --no-install-recommends git; \
        rm -rf /var/lib/apt/lists/*; \
        git clone --depth 1 https://github.com/FunAudioLLM/CosyVoice.git /opt/CosyVoice; \
        cd /opt/CosyVoice; \
        git submodule update --init --recursive; \
    fi

# 安装 VibeVoice 源码（直接使用仓库内置的 VibeVoice 目录）
RUN mkdir -p /opt/VibeVoice/demo
COPY VibeVoice/pyproject.toml VibeVoice/README.md VibeVoice/LICENSE /opt/VibeVoice/
COPY VibeVoice/vibevoice /opt/VibeVoice/vibevoice
COPY VibeVoice/demo/voices /opt/VibeVoice/demo/voices
RUN pip install --no-cache-dir --no-deps -e /opt/VibeVoice

# 复制服务端代码
COPY app /app
WORKDIR /app

ENV DATA_DIR=/data
ENV VOICES_DIR=/data/voices
ENV BUILTIN_VOICES_DIR=/opt/VibeVoice/demo/voices

EXPOSE 8000 80
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
