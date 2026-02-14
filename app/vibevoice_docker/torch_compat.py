from __future__ import annotations

import inspect
from typing import Any


def ensure_is_autocast_enabled_device_type_support(torch_mod: Any | None = None) -> bool:
    """Add ``device_type`` compatibility to ``torch.is_autocast_enabled``.

    Returns True when a compatibility wrapper is installed, False when the
    runtime already supports ``device_type`` natively.
    """

    if torch_mod is None:
        import torch as torch_mod  # type: ignore[no-redef]

    is_autocast_enabled = getattr(torch_mod, "is_autocast_enabled", None)
    if not callable(is_autocast_enabled):
        return False

    if getattr(is_autocast_enabled, "_supports_device_type", False):
        return False

    try:
        signature = inspect.signature(is_autocast_enabled)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        signature = None

    if signature is not None and len(signature.parameters) >= 1:
        return False

    def is_autocast_enabled_with_device_type(device_type: str | None = None):
        if device_type:
            backend_flag = getattr(torch_mod, f"is_autocast_{device_type}_enabled", None)
            if callable(backend_flag):
                return bool(backend_flag())

            backend_mod = getattr(torch_mod, device_type, None)
            backend_mod_flag = getattr(backend_mod, "is_autocast_enabled", None)
            if callable(backend_mod_flag):
                return bool(backend_mod_flag())

            try:
                return is_autocast_enabled(device_type)
            except TypeError:
                pass

        return is_autocast_enabled()

    is_autocast_enabled_with_device_type._supports_device_type = True  # type: ignore[attr-defined]
    torch_mod.is_autocast_enabled = is_autocast_enabled_with_device_type
    return True


def ensure_pad_sequence_padding_side_support(torch_mod: Any | None = None) -> bool:
    """Add ``padding_side`` compatibility to ``torch.nn.utils.rnn.pad_sequence``.

    Returns True when a compatibility wrapper is installed, False when the
    runtime already supports ``padding_side`` natively.
    """

    if torch_mod is None:
        import torch as torch_mod  # type: ignore[no-redef]

    rnn_utils = torch_mod.nn.utils.rnn
    pad_sequence = rnn_utils.pad_sequence

    try:
        signature = inspect.signature(pad_sequence)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        signature = None

    if signature is not None and "padding_side" in signature.parameters:
        return False

    if getattr(pad_sequence, "_supports_padding_side", False):
        return False

    def pad_sequence_with_padding_side(
        sequences,
        batch_first: bool = False,
        padding_value: float = 0.0,
        padding_side: str = "right",
    ):
        if padding_side == "right":
            return pad_sequence(
                sequences,
                batch_first=batch_first,
                padding_value=padding_value,
            )

        if padding_side != "left":
            raise ValueError("padding_side must be 'right' or 'left'")

        if not sequences:
            return pad_sequence(
                sequences,
                batch_first=batch_first,
                padding_value=padding_value,
            )

        lengths = [int(seq.size(0)) for seq in sequences]
        max_len = max(lengths)
        trailing_dims = sequences[0].size()[1:]
        if batch_first:
            out_dims = (len(sequences), max_len) + trailing_dims
        else:
            out_dims = (max_len, len(sequences)) + trailing_dims
        out_tensor = sequences[0].new_full(out_dims, padding_value)

        for index, seq in enumerate(sequences):
            length = int(seq.size(0))
            if batch_first:
                out_tensor[index, max_len - length :, ...] = seq
            else:
                out_tensor[max_len - length :, index, ...] = seq
        return out_tensor

    pad_sequence_with_padding_side._supports_padding_side = True  # type: ignore[attr-defined]
    rnn_utils.pad_sequence = pad_sequence_with_padding_side
    return True
