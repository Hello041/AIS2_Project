"""B-Free detector 테스트. 가중치·공식 코드가 없으면 건너뛴다 (download_weights.py --only bfree)."""
import csv

import numpy as np
import pytest
from PIL import Image

from detectors.bfree import NETWORKS, WEIGHTS, BFreeDetector

HAVE_WEIGHTS = (WEIGHTS / "model_epoch_best.pth").exists() and (NETWORKS / "__init__.py").exists()
needs_weights = pytest.mark.skipif(not HAVE_WEIGHTS, reason="B-Free 가중치 없음")
DEMO = NETWORKS.parent / "demo_images"


def test_missing_weights_message(monkeypatch, tmp_path):
    import detectors.bfree as b
    monkeypatch.setattr(b, "WEIGHTS", tmp_path)
    with pytest.raises(FileNotFoundError, match="download_weights.py"):
        BFreeDetector().load()


@pytest.fixture(scope="module")
def bfree():
    det = BFreeDetector()
    det.load()
    return det


@needs_weights
def test_matches_official_demo_results(bfree):
    """공식 저장소의 demo_images/results.csv(로짓)와 같은 값이 나오는지."""
    ref = {r["filename"]: float(r["BFREE_dino2reg4"]) for r in csv.DictReader(open(DEMO / "results.csv"))}
    labels = {r["filename"]: r["label"] for r in csv.DictReader(open(DEMO / "metainfo.csv"))}
    for fn, want in ref.items():
        img = Image.open(DEMO / fn).convert("RGB")
        assert bfree.logit(img) == pytest.approx(want, abs=1e-3)
        # 라벨 0(실제)은 0.5 미만, 1(AI)은 0.5 초과 → '클수록 AI' 방향 확인
        assert (bfree.score(img) > 0.5) == (labels[fn] != "0")


@needs_weights
@pytest.mark.parametrize("size,mode", [((640, 480), "RGB"), ((100, 80), "RGB"), ((300, 300), "RGBA"), ((257, 199), "L")])
def test_score_in_range_for_various_inputs(bfree, size, mode):
    rng = np.random.default_rng(0)
    shape = (size[1], size[0]) if mode == "L" else (size[1], size[0], len(mode))
    assert 0.0 <= bfree.score(Image.fromarray(rng.integers(0, 256, shape, dtype=np.uint8), mode)) <= 1.0
