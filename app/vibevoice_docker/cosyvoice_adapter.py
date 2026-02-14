from __future__ import annotations

import re


_SPEAKER_LINE_RE = re.compile(r"^\s*speaker\s*\d+\s*:\s*(.+?)\s*$", re.IGNORECASE)


def speaker_script_to_cosy_text(script: str) -> str:
    lines = [line.strip() for line in (script or "").splitlines() if line.strip()]
    if not lines:
        return "Hello."

    converted: list[str] = []
    for line in lines:
        m = _SPEAKER_LINE_RE.match(line)
        if m is None:
            converted.append(line)
            continue

        content = m.group(1).strip()
        if content:
            converted.append(content)

    if not converted:
        return "Hello."
    return " ".join(converted)


def _extract_prompt_excerpt(text: str, max_chars: int = 120) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return "Hello."

    sentence_break = re.search(r"[。！？.!?]", normalized)
    if sentence_break is not None:
        candidate = normalized[: sentence_break.start() + 1].strip()
        if candidate:
            return candidate[:max_chars].strip()

    return normalized[:max_chars].strip()


def build_cosy_prompt_text(prompt_text: str | None, tts_text: str) -> str:
    provided = (prompt_text or "").strip()
    if provided:
        return provided

    fallback = _extract_prompt_excerpt(tts_text)
    if fallback:
        return fallback
    return "Hello."
