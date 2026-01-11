from __future__ import annotations

import re


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SPEAKER_LINE_RE = re.compile(r"^\s*Speaker\s*(\d+)\s*:\s*(.*)$", re.IGNORECASE)


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
            out_lines.append(f"Speaker {speaker_id}: {cleaned}")

    if not out_lines:
        raise ValueError("No valid content found in input.")
    return "\n".join(out_lines)
