import importlib
import sys
import types
import unittest
from unittest.mock import patch


class FakeCudaTensor:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def __array__(self, dtype=None):
        raise TypeError(
            "can't convert cuda:0 device type tensor to numpy. "
            "Use Tensor.cpu() to copy the tensor to host memory first."
        )

    def detach(self):
        return self

    def to(self, *args, **kwargs):
        return self

    def reshape(self, *_shape):
        return self

    def numpy(self):
        import numpy as np

        return np.asarray(self._values, dtype=np.float32)


class TestInferenceSegments(unittest.TestCase):
    def setUp(self) -> None:
        self._torch_patch = None
        try:
            __import__("numpy")
        except ModuleNotFoundError as exc:
            self.skipTest(f"test dependencies missing: {exc}")

        try:
            __import__("torch")
        except ModuleNotFoundError:
            fake_torch = types.SimpleNamespace(
                cuda=types.SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None),
                dtype=type("dtype", (), {}),
                float16=object(),
                bfloat16=object(),
                float32=object(),
                Tensor=object,
                is_tensor=lambda _value: False,
            )
            self._torch_patch = patch.dict(sys.modules, {"torch": fake_torch})
            self._torch_patch.start()

        try:
            self.api_main = importlib.import_module("main")
        except ModuleNotFoundError as exc:
            self.skipTest(f"test dependencies missing: {exc}")

    def tearDown(self) -> None:
        if self._torch_patch is not None:
            self._torch_patch.stop()

    def test_run_inference_segments_converts_cuda_tensor_before_numpy(self) -> None:
        import numpy as np

        fake_torch = types.SimpleNamespace(
            Tensor=FakeCudaTensor,
            float32=object(),
        )
        with patch.dict(sys.modules, {"torch": fake_torch}):
            with patch.object(
                self.api_main,
                "_run_inference",
                return_value=(FakeCudaTensor([0.25, -0.5]), 24000),
            ):
                audio, sample_rate = self.api_main._run_inference_segments(
                    "vibevoice-7b",
                    [(object(), "hello")],
                    3.0,
                )

        self.assertEqual(24000, sample_rate)
        np.testing.assert_allclose(audio, np.asarray([0.25, -0.5], dtype=np.float32))
