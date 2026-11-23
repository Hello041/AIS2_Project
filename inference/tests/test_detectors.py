"""Detector 계약 테스트. 모델 가중치 없이 돈다."""
import io
import math

import numpy as np
import pytest
from PIL import Image

from detectors import (
    DEFAULT_DETECTORS, Detector, ScoreRangeError, active_names, check_score,
    create_detectors, get_detector_class, to_rgb,
)
from detectors.dummy import DummyDetector


@pytest.fixture
def img():
    return Image.new("RGB", (32, 32), (10, 20, 30))


# ---------------------------------------------------------------- check_score
@pytest.mark.parametrize("value", [0, 0.0, 0.5, 1, 1.0, np.float32(0.3), np.float64(1.0)])
def test_check_score_accepts_in_range(value):
    assert check_score(value) == pytest.approx(float(value))
    assert isinstance(check_score(value), float)


@pytest.mark.parametrize("value", [-1e-9, -0.1, 1.0000001, 1.5, 100, math.nan, math.inf, -math.inf])
def test_check_score_rejects_out_of_range(value):
    with pytest.raises(ScoreRangeError):
        check_score(value)


@pytest.mark.parametrize("value", [None, "0.5", [0.5], True, False])
def test_check_score_rejects_non_number(value):
    with pytest.raises(ScoreRangeError):
        check_score(value)


def test_check_score_accepts_0dim_tensor():
    torch = pytest.importorskip("torch")
    assert check_score(torch.tensor(0.25)) == pytest.approx(0.25)


# ---------------------------------------------------------------- to_rgb
@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "LA", "P", "CMYK", "I;16"])
def test_to_rgb_modes(mode):
    src = Image.new(mode, (8, 8))
    out = to_rgb(src)
    assert out.mode == "RGB" and out.size == (8, 8)


@pytest.mark.parametrize("bits16, expected", [(0, 0), (32896, 128), (65535, 255)])
def test_to_rgb_16bit_gray_is_scaled_not_clipped(bits16, expected):
    # 16비트 흑백 PNG가 거의 흰색으로 바뀌던 버그 (convert("RGB")가 255 넘는 값을 잘라냄)
    buf = io.BytesIO()
    Image.fromarray(np.full((4, 4), bits16, dtype=np.uint16)).save(buf, "PNG")
    buf.seek(0)
    with Image.open(buf) as src:
        assert to_rgb(src).getpixel((0, 0)) == (expected,) * 3


def test_to_rgb_transparent_becomes_white():
    src = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    assert to_rgb(src).getpixel((0, 0)) == (255, 255, 255)


# ---------------------------------------------------------------- Detector 계약
def test_detector_is_abstract():
    with pytest.raises(TypeError):
        Detector()


def test_score_requires_load(img):
    det = DummyDetector("univfd", 0.7)
    with pytest.raises(RuntimeError):
        det.score(img)


def test_dummy_returns_fixed_score(img):
    det = DummyDetector("bfree", 0.7)
    det.load()
    assert det.score(img) == 0.7
    assert det.name == "bfree"


@pytest.mark.parametrize("bad", [-0.01, 1.01, math.nan, 2])
def test_score_out_of_range_raises(img, bad):
    det = DummyDetector("aide", bad)
    det.load()
    with pytest.raises(ScoreRangeError, match="aide"):
        det.score(img)


def test_score_converts_to_rgb_before_model():
    seen = []

    class Spy(Detector):
        name = "spy"

        def _load(self):
            pass

        def _score(self, img):
            seen.append(img.mode)
            return 0.1

    det = Spy()
    det.load()
    det.score(Image.new("RGBA", (4, 4)))
    det.score(Image.new("L", (4, 4)))
    assert seen == ["RGB", "RGB"]


def test_load_called_once():
    count = []

    class Counting(Detector):
        name = "counting"

        def _load(self):
            count.append(1)

        def _score(self, img):
            return 0.0

    det = Counting()
    det.load()
    det.load()
    assert len(count) == 1 and det.loaded


def test_subclass_without_super_init_still_works(img):
    class NoSuper(Detector):
        name = "nosuper"

        def __init__(self):  # super().__init__()을 부르지 않음
            self.value = 0.2

        def _load(self):
            pass

        def _score(self, img):
            return self.value

    det = NoSuper()
    assert not det.loaded
    det.load()
    assert det.score(img) == 0.2


# ---------------------------------------------------------------- 레지스트리
def test_active_names_default(monkeypatch):
    monkeypatch.delenv("DETECTORS", raising=False)
    assert active_names() == list(DEFAULT_DETECTORS)


def test_active_names_from_env(monkeypatch):
    monkeypatch.setenv("DETECTORS", " UnivFD , bfree ,")
    assert active_names() == ["univfd", "bfree"]


def test_active_names_empty_env_means_default(monkeypatch):
    monkeypatch.setenv("DETECTORS", "  ")
    assert active_names() == list(DEFAULT_DETECTORS)


def test_active_names_rejects_duplicates():
    with pytest.raises(ValueError, match="중복"):
        active_names("bfree,bfree")


def test_create_detectors_from_env(monkeypatch, img):
    monkeypatch.setenv("DETECTORS", "dummy")
    (det,) = create_detectors(load=True)
    assert isinstance(det, DummyDetector) and det.loaded
    assert det.score(img) == 0.5


def test_get_detector_class():
    assert get_detector_class("dummy") is DummyDetector


@pytest.mark.parametrize("name", ["nope", "base", "../x", "Dummy", ""])
def test_unknown_or_invalid_name(name):
    with pytest.raises(ValueError):
        get_detector_class(name)


# ---------------------------------------------------------------- 추론 장치 (DEVICE)
def test_resolve_device_cpu_and_override():
    from detectors.base import resolve_device
    assert resolve_device("aide", {"DEVICE": "cpu"}) == "cpu"
    assert resolve_device("aide", {"DEVICE": "cuda", "DEVICE_AIDE": "cpu"}) == "cpu"  # 모델별 값이 우선
    assert resolve_device("aide", {"DEVICE": " CPU "}) == "cpu"


def test_resolve_device_rejects_bad_value():
    from detectors.base import resolve_device
    with pytest.raises(ValueError):
        resolve_device("aide", {"DEVICE": "gpu"})


def test_resolve_device_auto_and_cuda(monkeypatch):
    torch = pytest.importorskip("torch")
    from detectors.base import resolve_device
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert resolve_device("bfree", {}) == "cpu"                      # 기본 auto → GPU 없으면 CPU
    with pytest.raises(RuntimeError):
        resolve_device("bfree", {"DEVICE": "cuda"})                  # cuda는 GPU 필수
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 1)
    assert resolve_device("bfree", {}) == "cuda"
    assert resolve_device("bfree", {"DEVICE": "cuda:0"}) == "cuda:0"
    with pytest.raises(RuntimeError):
        resolve_device("bfree", {"DEVICE": "cuda:1"})


def test_load_sets_device(monkeypatch):
    from detectors.dummy import DummyDetector
    monkeypatch.setenv("DEVICE", "cpu")
    d = DummyDetector("dummy", 0.5)
    d.load()
    assert d.device == "cpu"
