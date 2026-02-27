from __future__ import annotations

import os
import re


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SPEAKER_LINE_RE = re.compile(r"^\s*Speaker\s*(\d+)\s*:\s*(.*)$", re.IGNORECASE)
_VOICE_TAG_LINE_RE = re.compile(r"^\s*\[([^\[\]\r\n]+)\]\s*(.*)$")

_ENV_SCRIPT_LINE_MAX_CHARS = "SCRIPT_LINE_MAX_CHARS"
_DEFAULT_SCRIPT_LINE_MAX_CHARS = 150
_SPLIT_BREAK_CHAR = "."


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def normalize_cn_punctuation_to_en_comma_period(text: str) -> str:
    """
    将中文/全角标点统一替换为英文逗号与句号（README Tips 推荐）。
    - 仅做字符级替换，不做复杂文本归一化。
    """
    if not text:
        return text

    # 句号类（包含中英文）
    period_like = {
        "。": ".",
        "！": ".",
        "？": ".",
        "；": ".",
        "…": ".",
        "．": ".",
        "!": ".",
        "?": ".",
        ";": ".",
    }
    # 逗号类（包含中英文）
    comma_like = {
        "，": ",",
        "、": ",",
        "：": ",",
        "—": ",",
        "－": ",",
        "～": ",",
        ":": ",",
    }

    # 这些符号直接删除（不转成逗号），避免产生不必要停顿
    delete_like = {
        "（",
        "）",
        "(",
        ")",
        "【",
        "】",
        "[",
        "]",
        "{",
        "}",
        "「",
        "」",
        "『",
        "』",
        "《",
        "》",
        "“",
        "”",
        "‘",
        "’",
        "\"",
        "'",
    }

    out = []
    for ch in text:
        if ch in delete_like:
            continue
        if ch in comma_like:
            out.append(",")
        elif ch in period_like:
            out.append(".")
        elif ch in {"\r", "\n"}:
            out.append(".")
        else:
            out.append(ch)

    # 合并连续标点，避免 ",,," 或 "..." 过长
    normalized = "".join(out)
    normalized = re.sub(r"\s*,\s*", ",", normalized)
    normalized = re.sub(r"\s*\.\s*", ".", normalized)
    normalized = re.sub(r",{2,}", ",", normalized)
    normalized = re.sub(r"\.{2,}", ".", normalized)
    return normalized


def looks_like_speaker_script(text: str) -> bool:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return bool(_SPEAKER_LINE_RE.match(first))


def _get_script_line_max_chars() -> int:
    """
    获取单一 Speaker 脚本单行文本长度上限（按 Python 字符数 len 计）。

    - 默认：150
    - 通过环境变量覆盖：SCRIPT_LINE_MAX_CHARS
    - 设置为 0 或负数：禁用自动拆分
    """
    raw = (os.environ.get(_ENV_SCRIPT_LINE_MAX_CHARS) or "").strip()
    if not raw:
        return _DEFAULT_SCRIPT_LINE_MAX_CHARS
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_SCRIPT_LINE_MAX_CHARS


def _split_text_by_max_chars(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]

    remaining = text
    parts: list[str] = []
    min_cut = max(1, max_chars // 2)

    while len(remaining) > max_chars:
        cut_at = None

        period_idx = remaining.rfind(_SPLIT_BREAK_CHAR, min_cut, max_chars)
        if period_idx >= 0:
            cut_at = period_idx + 1

        if cut_at is None:
            cut_at = max_chars

        head = remaining[:cut_at].strip()
        if head:
            parts.append(head)
        remaining = remaining[cut_at:].strip()

        if not remaining:
            break

    if remaining:
        parts.append(remaining)
    return parts


def _normalize_and_split_text(
    text: str,
    *,
    enable_cn_punct_normalize: bool,
    max_chars_per_line: int,
) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    if enable_cn_punct_normalize and contains_cjk(cleaned):
        cleaned = normalize_cn_punctuation_to_en_comma_period(cleaned)

    cleaned = cleaned.strip()
    if not cleaned:
        return []
    return _split_text_by_max_chars(cleaned, max_chars_per_line)


def normalize_speaker_script(script: str, *, enable_cn_punct_normalize: bool) -> str:
    """
    将输入脚本归一化为标准 Speaker 脚本。

    规则：
    - 支持单说话人与多说话人（`Speaker N:` / `SpeakerN:`）
    - 支持行格式：SpeakerN: / Speaker N:（大小写不敏感）
    - 对冒号后的文本部分：可选中文标点归一化（字符级替换）
    - 若遇到未带 Speaker 前缀的行：视为延续上一行的同一 Speaker
    """
    if not script or not script.strip():
        raise ValueError("input is empty")

    out_lines: list[str] = []
    current_speaker_id: int | None = None
    max_chars_per_line = _get_script_line_max_chars()

    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = _SPEAKER_LINE_RE.match(line)
        if match:
            speaker_id = int(match.group(1))
            text = match.group(2).strip()
            current_speaker_id = speaker_id
        else:
            if current_speaker_id is None:
                raise ValueError(f"Invalid script line (missing Speaker prefix): {line}")
            text = line

        for part in _normalize_and_split_text(
            text,
            enable_cn_punct_normalize=enable_cn_punct_normalize,
            max_chars_per_line=max_chars_per_line,
        ):
            out_lines.append(f"Speaker {current_speaker_id}: {part}")

    if not out_lines:
        raise ValueError("No valid content found in input.")
    return "\n".join(out_lines)


def normalize_single_speaker_script(script: str, *, enable_cn_punct_normalize: bool) -> str:
    """
    兼容旧函数名：当前行为与 normalize_speaker_script 一致。
    """
    return normalize_speaker_script(
        script,
        enable_cn_punct_normalize=enable_cn_punct_normalize,
    )


def normalize_script_to_voice_segments(
    script: str,
    *,
    default_voice_id: str,
    enable_cn_punct_normalize: bool,
) -> list[tuple[str, str]]:
    """
    归一化输入文本，并解析为 (voice_id, text) 列表。

    支持两类输入：
    - `[voice_id]文本` + 同 speaker 的续行文本（无前缀）
    - `Speaker N: 文本` / 普通文本（都回退到 default_voice_id）
    """
    normalized_input = (script or "").strip()
    if not normalized_input:
        raise ValueError("input is empty")

    fallback_voice_id = (default_voice_id or "").strip()
    if not fallback_voice_id:
        raise ValueError("default_voice_id is required")

    max_chars_per_line = _get_script_line_max_chars()
    raw_lines = [line.strip() for line in normalized_input.splitlines() if line.strip()]

    if any(_VOICE_TAG_LINE_RE.match(line) is not None for line in raw_lines):
        out_segments: list[tuple[str, str]] = []
        current_voice_id = fallback_voice_id

        for line in raw_lines:
            tagged = _VOICE_TAG_LINE_RE.match(line)
            if tagged is not None:
                tagged_voice_id = tagged.group(1).strip()
                if not tagged_voice_id:
                    raise ValueError(f"Invalid voice tag line: {line}")
                current_voice_id = tagged_voice_id
                text = tagged.group(2).strip()
            else:
                text = line

            for part in _normalize_and_split_text(
                text,
                enable_cn_punct_normalize=enable_cn_punct_normalize,
                max_chars_per_line=max_chars_per_line,
            ):
                out_segments.append((current_voice_id, part))

        if not out_segments:
            raise ValueError("No valid content found in input.")
        return out_segments

    speaker_script = normalized_input
    if not looks_like_speaker_script(speaker_script):
        speaker_script = f"Speaker 0: {speaker_script}"

    normalized_speaker_script = normalize_speaker_script(
        speaker_script,
        enable_cn_punct_normalize=enable_cn_punct_normalize,
    )

    out_segments: list[tuple[str, str]] = []
    for line in normalized_speaker_script.splitlines():
        match = _SPEAKER_LINE_RE.match(line)
        if match is None:
            continue
        text = match.group(2).strip()
        if text:
            out_segments.append((fallback_voice_id, text))

    if not out_segments:
        raise ValueError("No valid content found in input.")
    return out_segments
