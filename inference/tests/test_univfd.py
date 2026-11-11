"""UnivFD detector 테스트. 가중치·공식 코드가 없으면 건너뛴다 (download_weights.py --only univfd)."""
import numpy as np
import pytest
from PIL import Image

from detectors.univfd import CLIP_MODEL_PY, WEIGHTS, UnivFDDetector, build_transform

HAVE_WEIGHTS = (WEIGHTS / "ViT-L-14.pt").exists() and (WEIGHTS / "fc_weights.pth").exists() and CLIP_MODEL_PY.exists()
needs_weights = pytest.mark.skipif(not HAVE_WEIGHTS, reason="UnivFD 가중치 없음")


def test_invalid_preprocess_mode_rejected():
    with pytest.raises(ValueError):
        UnivFDDetector(preprocess="bogus")


@pytest.mark.parametrize("mode", ["crop", "resize"])
def test_transform_output_shape(mode):
    x = build_transform(mode)(Image.new("RGB", (1000, 600)))
    assert tuple(x.shape) == (3, 224, 224)


def test_missing_weights_message(monkeypatch, tmp_path):
    import detectors.univfd as u
    monkeypatch.setattr(u, "WEIGHTS", tmp_path)
    det = UnivFDDetector()
    with pytest.raises(FileNotFoundError, match="download_weights.py"):
        det.load()


@pytest.fixture(scope="module")
def univfd():
    det = UnivFDDetector(preprocess="crop")
    det.load()
    return det


@needs_weights
def test_only_image_encoder_loaded(univfd):
    # 텍스트 인코더(token_embedding, transformer 등)는 만들지 않는다
    names = {n for n, _ in univfd._visual.named_parameters()}
    assert "conv1.weight" in names and not any(n.startswith("token_embedding") for n in names)


@needs_weights
@pytest.mark.parametrize("size,mode", [((640, 480), "RGB"), ((100, 80), "RGB"), ((300, 300), "RGBA"), ((257, 199), "L")])
def test_score_in_range_for_various_inputs(univfd, size, mode):
    rng = np.random.default_rng(0)
    arr = rng.integers(0, 256, (size[1], size[0], len(mode)) if mode != "L" else (size[1], size[0]), dtype=np.uint8)
    s = univfd.score(Image.fromarray(arr, mode))
    assert 0.0 <= s <= 1.0


@needs_weights
def test_deterministic(univfd):
    img = Image.new("RGB", (512, 512), (120, 140, 160))
    assert univfd.score(img) == univfd.score(img)
