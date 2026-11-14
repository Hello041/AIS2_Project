"""Community Forensics detector 테스트. 가중치가 없으면 건너뛴다 (download_weights.py --only commfor)."""
import csv
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from detectors.commfor import INFERENCE, WEIGHTS, CommForDetector

HAVE_WEIGHTS = (WEIGHTS / "model.safetensors").exists() and (WEIGHTS / "config.json").exists()
needs_weights = pytest.mark.skipif(not HAVE_WEIGHTS, reason="Community Forensics 가중치 없음")
OFFICIAL_TEST_IMAGES = INFERENCE / "third_party" / "commfor" / "test_images"   # 공식 저장소의 DALL-E 2 이미지
DATA = Path(__file__).resolve().parents[2] / "ml" / "data"
SCORES = Path(__file__).resolve().parents[2] / "ml" / "scores.csv"


def test_missing_weights_message(monkeypatch, tmp_path):
    import detectors.commfor as c
    monkeypatch.setattr(c, "WEIGHTS", tmp_path)
    with pytest.raises(FileNotFoundError, match="commfor-model-384"):
        CommForDetector().load()


@pytest.fixture(scope="module")
def commfor():
    det = CommForDetector()
    det.load()
    return det


@needs_weights
@pytest.mark.skipif(not OFFICIAL_TEST_IMAGES.exists(), reason="공식 코드(test_images) 없음")
def test_official_test_images_are_ai(commfor):
    """공식 예제 이미지(DALL-E 2 생성)는 모두 0.5 초과 → '클수록 AI' 방향 확인 (2026-11-14: 0.79~1.00)."""
    files = sorted(OFFICIAL_TEST_IMAGES.glob("*.png"))
    assert files
    for f in files:
        with Image.open(f) as img:
            assert commfor.score(img) > 0.5, f.name


@needs_weights
@pytest.mark.skipif(not SCORES.exists(), reason="ml/scores.csv 없음")
def test_matches_recorded_scores(commfor):
    """scores.csv에 기록된 점수(같은 detector 코드로 채점)와 같은지 — 전처리·가중치가 바뀌면 깨진다."""
    rows = [r for r in csv.DictReader(open(SCORES, encoding="utf-8")) if r["version"] == "original"][:3]
    rows += [r for r in csv.DictReader(open(SCORES, encoding="utf-8")) if r["label"] == "ai"][:3]
    paths = {m["image_id"]: DATA / m["file_path"]
             for m in csv.DictReader(open(DATA / "manifest.csv", encoding="utf-8-sig"))}
    checked = 0
    for r in rows:
        path = paths.get(r["image_id"])
        if path is None or not path.exists():
            continue
        with Image.open(path) as img:
            assert commfor.score(img) == pytest.approx(float(r["commfor"]), abs=1e-5)
        checked += 1
    if not checked:
        pytest.skip("검증 이미지 없음")


@needs_weights
@pytest.mark.parametrize("size,mode", [((640, 480), "RGB"), ((40, 30), "RGB"), ((300, 300), "RGBA"), ((257, 199), "L")])
def test_score_in_range_for_various_inputs(commfor, size, mode):
    rng = np.random.default_rng(0)
    shape = (size[1], size[0]) if mode == "L" else (size[1], size[0], len(mode))
    assert 0.0 <= commfor.score(Image.fromarray(rng.integers(0, 256, shape, dtype=np.uint8), mode)) <= 1.0
