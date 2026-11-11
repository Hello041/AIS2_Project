"""AIDE detector 테스트. 가중치·공식 코드가 없으면 건너뛴다 (download_weights.py --only aide).

AIDE는 로드에 20초 이상, 메모리 최대 약 7GB가 든다. 모듈 단위로 한 번만 로드한다.
"""
import numpy as np
import pytest
from PIL import Image

from detectors.aide import CHECKPOINT, REPO, AIDEDetector

HAVE_WEIGHTS = CHECKPOINT.exists() and (REPO / "models" / "AIDE.py").exists()
needs_weights = pytest.mark.skipif(not HAVE_WEIGHTS, reason="AIDE 가중치 없음")


def test_missing_weights_message(monkeypatch, tmp_path):
    import detectors.aide as a
    monkeypatch.setattr(a, "CHECKPOINT", tmp_path / "none.pth")
    with pytest.raises(FileNotFoundError, match="download_weights.py"):
        AIDEDetector().load()


@pytest.mark.parametrize("size,expected", [((16, 16), (32, 32)), ((20, 100), (32, 160)), ((64, 40), (64, 40))])
def test_min_side(size, expected):
    assert AIDEDetector._ensure_min_side(Image.new("RGB", size)).size == expected


@pytest.fixture(scope="module")
def aide():
    det = AIDEDetector()
    det.load()
    return det


@needs_weights
@pytest.mark.parametrize("size,mode", [((640, 480), "RGB"), ((16, 16), "RGB"), ((300, 300), "RGBA"), ((257, 199), "L")])
def test_score_in_range_for_various_inputs(aide, size, mode):
    rng = np.random.default_rng(0)
    shape = (size[1], size[0]) if mode == "L" else (size[1], size[0], len(mode))
    s = aide.score(Image.fromarray(rng.integers(0, 256, shape, dtype=np.uint8), mode))
    assert 0.0 <= s <= 1.0


@needs_weights
def test_deterministic(aide):
    img = Image.new("RGB", (512, 384), (90, 120, 150))
    assert aide.score(img) == aide.score(img)
