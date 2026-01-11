"""
在镜像构建阶段下载 VibeVoice 模型。

说明：
- 根据 `VIBEVOICE_MODEL_ID` 下载单个模型权重，用于构建“固定模型”的镜像。
- 可通过环境变量覆盖下载目录，便于调试/复用。

环境变量：
- VIBEVOICE_MODELS_DIR: 模型落盘目录，默认 /models
- VIBEVOICE_MODEL_ID: 模型选择（vibevoice-1.5b / vibevoice-7b）
- VIBEVOICE_MODELSCOPE_REVISION: ModelScope revision（可选；默认用仓库默认 revision）
- MODELSCOPE_CACHE: ModelScope 下载缓存目录（建议指向临时目录，如 /tmp/modelscope-cache）
- VIBEVOICE_EXPECTED_INDEX_SHA256: 校验 model.safetensors.index.json 的 sha256（可选；为空则使用脚本内置值）
- VIBEVOICE_CLEAN_MODELSCOPE_CACHE: 是否清理 MODELSCOPE_CACHE（默认 1；设为 0/false/no 可保留）
"""

import os
import shutil
from hashlib import sha256
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


def _expected_index_sha256(model_id: str) -> Optional[str]:
    # 说明：
    # - ModelScope 仓库目前只有 master 分支，缺少可用 tag；这里用关键文件 sha256 作为“可重复构建”的锚点
    # - 该值与 ModelScope 模型页展示的 model.safetensors.index.json 的 sha256 对齐
    # - 若上游更新了模型文件，构建会显式失败，避免悄悄引入不可控变化
    if model_id == "vibevoice-1.5b":
        return "067db9b10fdecee3a5588aa00206794156c7125f5e85f3f2234e0e6d821ee629"
    if model_id == "vibevoice-7b":
        return "dbcfc6e307494bc87684471872f3d8b785cb68b3589b6b306c43fde629b88ebd"
    return None


def _sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    models_dir = Path(os.getenv("VIBEVOICE_MODELS_DIR", "/models"))
    model_id = _normalize_model_id(os.getenv("VIBEVOICE_MODEL_ID"))
    modelscope_repo_id = _to_modelscope_repo_id(model_id)

    revision = (os.getenv("VIBEVOICE_MODELSCOPE_REVISION") or "").strip() or None
    cache_dir = (os.getenv("MODELSCOPE_CACHE") or "").strip() or None

    local_dir = models_dir / modelscope_repo_id.split("/", 1)[-1]
    local_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        model_id=modelscope_repo_id,
        revision=revision,
        cache_dir=cache_dir,
        local_dir=str(local_dir),
        max_workers=8,
    )

    expected = (os.getenv("VIBEVOICE_EXPECTED_INDEX_SHA256") or "").strip() or _expected_index_sha256(model_id)
    if expected:
        index_path = local_dir / "model.safetensors.index.json"
        if not index_path.exists():
            raise FileNotFoundError(f"Missing model index file: {index_path}")

        actual = _sha256_file(index_path)
        if actual.lower() != expected.lower():
            raise ValueError(
                "Model index sha256 mismatch. "
                f"expected={expected.lower()} actual={actual.lower()} path={index_path}"
            )

    # 可选清理：避免把临时 cache 目录打进镜像层（有助于稳定 layer digest）
    clean_cache = (os.getenv("VIBEVOICE_CLEAN_MODELSCOPE_CACHE") or "1").strip().lower() not in {"0", "false", "no"}
    if clean_cache and cache_dir:
        cache_path = Path(cache_dir)
        if cache_path.exists():
            shutil.rmtree(cache_path, ignore_errors=True)


if __name__ == "__main__":
    main()
