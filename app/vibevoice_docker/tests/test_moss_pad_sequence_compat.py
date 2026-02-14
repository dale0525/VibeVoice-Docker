import importlib
import unittest


class TestMossPadSequenceCompat(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.torch = importlib.import_module("torch")
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
            self.skipTest(f"torch is not installed in local test environment: {exc}")
        self.torch_compat = importlib.import_module("vibevoice_docker.torch_compat")

    def test_adds_padding_side_support_for_older_torch(self) -> None:
        torch = self.torch
        rnn_utils = torch.nn.utils.rnn
        original_pad_sequence = rnn_utils.pad_sequence

        call_count = {"right": 0}

        def old_pad_sequence(sequences, batch_first=False, padding_value=0.0):
            call_count["right"] += 1
            lengths = [int(s.size(0)) for s in sequences]
            max_len = max(lengths)
            trailing_dims = sequences[0].size()[1:]
            if batch_first:
                out_dims = (len(sequences), max_len) + trailing_dims
            else:
                out_dims = (max_len, len(sequences)) + trailing_dims
            out = sequences[0].new_full(out_dims, padding_value)
            for idx, tensor in enumerate(sequences):
                length = int(tensor.size(0))
                if batch_first:
                    out[idx, :length, ...] = tensor
                else:
                    out[:length, idx, ...] = tensor
            return out

        try:
            rnn_utils.pad_sequence = old_pad_sequence
            self.torch_compat.ensure_pad_sequence_padding_side_support(torch_mod=torch)

            seq_a = torch.tensor([1, 2, 3])
            seq_b = torch.tensor([4, 5])

            left_padded = rnn_utils.pad_sequence(
                [seq_a, seq_b],
                batch_first=True,
                padding_value=0,
                padding_side="left",
            )
            self.assertTrue(torch.equal(left_padded, torch.tensor([[1, 2, 3], [0, 4, 5]])))

            right_padded = rnn_utils.pad_sequence(
                [seq_a, seq_b],
                batch_first=True,
                padding_value=0,
                padding_side="right",
            )
            self.assertTrue(torch.equal(right_padded, torch.tensor([[1, 2, 3], [4, 5, 0]])))
            self.assertGreaterEqual(call_count["right"], 1)
        finally:
            rnn_utils.pad_sequence = original_pad_sequence
