"""
在镜像构建阶段下载 VibeVoice 模型。

说明：
- 根据 `VIBEVOICE_MODEL_ID` 下载单个模型权重，用于构建“固定模型”的镜像。
- 可通过环境变量覆盖下载目录，便于调试/复用。

环境变量：
- VIBEVOICE_MODELS_DIR: 模型落盘目录，默认 /models
- VIBEVOICE_MODEL_ID: 模型选择（vibevoice-1.5b / vibevoice-7b）
"""

import os
from pathlib import Path
from typing import Optional

from modelscope.hub.snapshot_download import snapshot_download


def _normalize_model_id(value: Optional[str]) -> str:
    if not value:
        return "vibevoice-1.5b"

    v = value.strip().lower()
    if v in {"vibevoice-1.5b", "1.5b", "vibevoice-1.5"}:
        return "vibevoice-1.5b"
    if v in {"vibevoice-7b", "7b", "vibevoice-7"}:
        return "vibevoice-7b"
    raise ValueError(f"Unsupported VIBEVOICE_MODEL_ID: {value!r}")


def _to_modelscope_repo_id(model_id: str) -> str:
    if model_id == "vibevoice-1.5b":
        return "microsoft/VibeVoice-1.5B"
    if model_id == "vibevoice-7b":
        return "microsoft/VibeVoice-7B"
    raise ValueError(f"Unsupported model_id: {model_id!r}")


def main() -> None:
    models_dir = Path(os.getenv("VIBEVOICE_MODELS_DIR", "/models"))
    model_id = _normalize_model_id(os.getenv("VIBEVOICE_MODEL_ID"))
    modelscope_repo_id = _to_modelscope_repo_id(model_id)

    local_dir = models_dir / modelscope_repo_id.split("/", 1)[-1]
    local_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        model_id=modelscope_repo_id,
        local_dir=str(local_dir),
        max_workers=8,
    )


if __name__ == "__main__":
    main()
