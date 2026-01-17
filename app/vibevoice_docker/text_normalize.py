from __future__ import annotations

import os
import re


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SPEAKER_LINE_RE = re.compile(r"^\s*Speaker\s*(\d+)\s*:\s*(.*)$", re.IGNORECASE)

_ENV_SCRIPT_LINE_MAX_CHARS = "VIBEVOICE_SCRIPT_LINE_MAX_CHARS"
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
    - 通过环境变量覆盖：VIBEVOICE_SCRIPT_LINE_MAX_CHARS
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


def normalize_single_speaker_script(script: str, *, enable_cn_punct_normalize: bool) -> str:
    """
    将输入脚本归一化为“单一说话人脚本”。

    规则：
    - 仅允许出现一种 Speaker 编号（例如全是 Speaker 0 或全是 Speaker 1），否则抛出 ValueError
    - 支持行格式：SpeakerN: / Speaker N:（大小写不敏感）
    - 对冒号后的文本部分：可选中文标点归一化（字符级替换）
    - 若遇到未带 Speaker 前缀的行：视为延续上一行的同一 Speaker
    """
    if not script or not script.strip():
        raise ValueError("input is empty")

    out_lines: list[str] = []
    speaker_ids: set[int] = set()
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
            speaker_id = current_speaker_id
            text = line

        speaker_ids.add(speaker_id)
        if len(speaker_ids) > 1:
            raise ValueError("Multi-speaker script is not supported (only one Speaker id is allowed).")

        if enable_cn_punct_normalize and contains_cjk(text):
            text = normalize_cn_punctuation_to_en_comma_period(text)

        cleaned = text.strip()
        if cleaned:
            for part in _split_text_by_max_chars(cleaned, max_chars_per_line):
                out_lines.append(f"Speaker {speaker_id}: {part}")

    if not out_lines:
        raise ValueError("No valid content found in input.")
    return "\n".join(out_lines)
