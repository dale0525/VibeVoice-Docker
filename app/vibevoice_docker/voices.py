from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal
from uuid import uuid4


VoiceType = Literal["builtin", "custom"]


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\\-\\_]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "voice"


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    type: VoiceType
    sample_path: Path
    created_at: int


class VoiceStore:
    def __init__(self, builtin_dir: Path, custom_dir: Path):
        self._builtin_dir = builtin_dir
        self._custom_dir = custom_dir

    def ensure_dirs(self) -> None:
        self._custom_dir.mkdir(parents=True, exist_ok=True)

    def list_voices(self) -> list[Voice]:
        voices: list[Voice] = []

        # Builtin voices: *.wav in builtin_dir
        if self._builtin_dir.exists():
            for wav_path in sorted(self._builtin_dir.glob("*.wav")):
                voices.append(
                    Voice(
                        id=wav_path.stem,
                        name=wav_path.stem,
                        type="builtin",
                        sample_path=wav_path,
                        created_at=0,
                    )
                )

        # Custom voices: <id>/voice.json + sample.wav
        if self._custom_dir.exists():
            for voice_dir in sorted([p for p in self._custom_dir.iterdir() if p.is_dir()]):
                meta_path = voice_dir / "voice.json"
                sample_path = voice_dir / "sample.wav"
                if not meta_path.exists() or not sample_path.exists():
                    continue
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                voices.append(
                    Voice(
                        id=str(meta.get("id") or voice_dir.name),
                        name=str(meta.get("name") or voice_dir.name),
                        type="custom",
                        sample_path=sample_path,
                        created_at=int(meta.get("created_at") or 0),
                    )
                )

        return voices

    def get_voice(self, voice_id: str) -> Voice | None:
        for v in self.list_voices():
            if v.id == voice_id:
                return v
        return None

    def create_voice(self, name: str, sample_wav_path: Path) -> Voice:
        self.ensure_dirs()

        now = int(time.time())
        voice_id = f"{_slugify(name)}-{uuid4().hex[:8]}"
        voice_dir = self._custom_dir / voice_id
        voice_dir.mkdir(parents=True, exist_ok=False)

        stored_sample = voice_dir / "sample.wav"
        shutil.copy2(sample_wav_path, stored_sample)

        meta = {
            "id": voice_id,
            "name": name,
            "created_at": now,
        }
        (voice_dir / "voice.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        return Voice(
            id=voice_id,
            name=name,
            type="custom",
            sample_path=stored_sample,
            created_at=now,
        )

    def delete_voice(self, voice_id: str) -> bool:
        voice_dir = self._custom_dir / voice_id
        if not voice_dir.exists():
            return False
        shutil.rmtree(voice_dir)
        return True

