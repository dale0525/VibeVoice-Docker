from __future__ import annotations

import re


_SPEAKER_LINE_RE = re.compile(r"^\s*speaker\s*(\d+)\s*:\s*(.+?)\s*$", re.IGNORECASE)
_MOSS_TAG_RE = re.compile(r"\[S\d+\]")


def _ensure_moss_speaker_tag(text: str, speaker_id: int = 1) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return f"[S{speaker_id}] Hello."
    expected = f"[S{speaker_id}]"
    if stripped.startswith(expected):
        return stripped
    return f"{expected} {stripped}"


def speaker_script_to_moss_text(script: str) -> str:
    lines = [line.strip() for line in (script or "").splitlines() if line.strip()]
    if not lines:
        return "[S1] Hello."

    converted: list[str] = []
    for line in lines:
        m = _SPEAKER_LINE_RE.match(line)
        if m is None:
            converted.append(_ensure_moss_speaker_tag(line, speaker_id=1))
            continue

        original_speaker_id = int(m.group(1))
        speaker_id = max(1, original_speaker_id + 1)
        content = m.group(2).strip()
        if content:
            converted.append(f"[S{speaker_id}] {content}")

    if not converted:
        return "[S1] Hello."
    return " ".join(converted)


def _extract_dialogue_excerpt(moss_text: str, max_chars: int = 120) -> str:
    text = _MOSS_TAG_RE.sub(" ", moss_text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "Hello."

    sentence_break = re.search(r"[。！？.!?]", text)
    if sentence_break is not None:
        candidate = text[: sentence_break.start() + 1].strip()
        if candidate:
            return candidate[:max_chars].strip()

    return text[:max_chars].strip()


def build_moss_prompt_text(prompt_text: str | None, moss_text: str) -> str:
    provided = (prompt_text or "").strip()
    if provided:
        return _ensure_moss_speaker_tag(provided, speaker_id=1)

    fallback = _extract_dialogue_excerpt(moss_text)
    return _ensure_moss_speaker_tag(fallback, speaker_id=1)
