"""
在镜像构建阶段下载模型文件。

环境变量：
- VIBEVOICE_MODELS_DIR: 模型落盘目录，默认 /models
- VIBEVOICE_MODEL_ID: 模型选择（vibevoice-1.5b / vibevoice-7b / moss-ttsd-v1.0）
- VIBEVOICE_MODELSCOPE_REVISION: ModelScope revision（可选）
- MODELSCOPE_CACHE: ModelScope 下载缓存目录（建议指向临时目录）
- VIBEVOICE_EXPECTED_INDEX_SHA256: 仅对 VibeVoice 生效，可覆盖默认 sha256 校验值
- VIBEVOICE_CLEAN_MODELSCOPE_CACHE: 是否清理 MODELSCOPE_CACHE（默认 1）
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Optional

from modelscope.hub.snapshot_download import snapshot_download


@dataclass(frozen=True)
class DownloadTarget:
    repo_id: str
    local_dir_name: str
    expected_index_sha256: Optional[str] = None


def _normalize_model_id(value: Optional[str]) -> str:
    if not value:
        return "vibevoice-1.5b"

    v = value.strip().lower()
    if v in {"vibevoice-1.5b", "1.5b", "vibevoice-1.5"}:
        return "vibevoice-1.5b"
    if v in {"vibevoice-7b", "7b", "vibevoice-7"}:
        return "vibevoice-7b"
    if v in {"moss-ttsd-v1.0", "moss_ttsd", "moss-ttsd", "moss"}:
        return "moss-ttsd-v1.0"
    raise ValueError(f"Unsupported VIBEVOICE_MODEL_ID: {value!r}")


def _default_vibevoice_index_sha256(model_id: str) -> Optional[str]:
    if model_id == "vibevoice-1.5b":
        return "067db9b10fdecee3a5588aa00206794156c7125f5e85f3f2234e0e6d821ee629"
    if model_id == "vibevoice-7b":
        return "dbcfc6e307494bc87684471872f3d8b785cb68b3589b6b306c43fde629b88ebd"
    return None


def _build_targets(model_id: str) -> list[DownloadTarget]:
    if model_id == "vibevoice-1.5b":
        return [
            DownloadTarget(
                repo_id="microsoft/VibeVoice-1.5B",
                local_dir_name="VibeVoice-1.5B",
                expected_index_sha256=_default_vibevoice_index_sha256(model_id),
            )
        ]
    if model_id == "vibevoice-7b":
        return [
            DownloadTarget(
                repo_id="microsoft/VibeVoice-7B",
                local_dir_name="VibeVoice-7B",
                expected_index_sha256=_default_vibevoice_index_sha256(model_id),
            )
        ]
    if model_id == "moss-ttsd-v1.0":
        return [
            DownloadTarget(
                repo_id="openmoss/MOSS-TTSD-v1.0",
                local_dir_name="MOSS-TTSD-v1.0",
            ),
            DownloadTarget(
                repo_id="openmoss/MOSS-Audio-Tokenizer",
                local_dir_name="MOSS-Audio-Tokenizer",
            ),
        ]
    raise ValueError(f"Unsupported model_id: {model_id!r}")


def _sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_index_sha256(local_dir: Path, expected_sha256: str) -> None:
    index_path = local_dir / "model.safetensors.index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Missing model index file: {index_path}")

    actual = _sha256_file(index_path)
    if actual.lower() != expected_sha256.lower():
        raise ValueError(
            "Model index sha256 mismatch. "
            f"expected={expected_sha256.lower()} actual={actual.lower()} path={index_path}"
        )


def main() -> None:
    models_dir = Path(os.getenv("VIBEVOICE_MODELS_DIR", "/models"))
    model_id = _normalize_model_id(os.getenv("VIBEVOICE_MODEL_ID"))
    revision = (os.getenv("VIBEVOICE_MODELSCOPE_REVISION") or "").strip() or None
    cache_dir = (os.getenv("MODELSCOPE_CACHE") or "").strip() or None

    targets = _build_targets(model_id)
    for idx, target in enumerate(targets):
        local_dir = models_dir / target.local_dir_name
        local_dir.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            model_id=target.repo_id,
            revision=revision,
            cache_dir=cache_dir,
            local_dir=str(local_dir),
            max_workers=8,
        )

        expected_sha = target.expected_index_sha256
        # 兼容旧环境变量：仅在下载单个 VibeVoice 模型时允许全局覆盖。
        if len(targets) == 1 and idx == 0:
            env_sha = (os.getenv("VIBEVOICE_EXPECTED_INDEX_SHA256") or "").strip()
            if env_sha:
                expected_sha = env_sha
        if expected_sha:
            _verify_index_sha256(local_dir, expected_sha)

    clean_cache = (os.getenv("VIBEVOICE_CLEAN_MODELSCOPE_CACHE") or "1").strip().lower() not in {"0", "false", "no"}
    if clean_cache and cache_dir:
        cache_path = Path(cache_dir)
        if cache_path.exists():
            shutil.rmtree(cache_path, ignore_errors=True)


if __name__ == "__main__":
    main()
