"""robustness.py 테스트. 가짜 모델로 가중치 없이 돈다."""
import pytest
from PIL import Image

import banding
import robustness as rob
from detectors import Detector

TH = {"a": (0.3, 0.7), "b": (0.3, 0.7), "c": (0.3, 0.7)}


class Fake(Detector):
    """이미지 크기·형식에 따라 점수를 바꿔, 변형마다 다른 구간이 나오게 한다."""

    def __init__(self, name, by_width=None, default=0.9):
        super().__init__()
        self.name, self.by_width, self.default, self.seen = name, by_width or {}, default, []

    def _load(self):
        pass

    def _score(self, img):
        self.seen.append(img.size)
        return self.by_width.get(img.width, self.default)


@pytest.fixture(autouse=True)
def thresholds(monkeypatch):
    real_band = banding.band
    monkeypatch.setattr(banding, "band", lambda n, s, t=None: real_band(n, s, TH))


def loaded(*dets):
    for d in dets:
        d.load()
    return list(dets)


IMG = Image.new("RGB", (400, 300), (10, 20, 30))  # resize50 → 200px, screenshot은 그대로 400px


def test_names_and_order_follow_plan():
    out = rob.robustness(IMG, loaded(Fake("a"), Fake("b"), Fake("c")))
    assert [r["variant"] for r in out] == ["original", "jpeg", "resize", "screenshot"]
    assert all(r["band"] == "strong" for r in out)


def test_variant_changes_overall_band():
    # 축소본(가로 200)에서만 두 모델이 weak → 그 버전만 weak
    dets = loaded(Fake("a", {200: 0.1}), Fake("b", {200: 0.1}), Fake("c"))
    out = {r["variant"]: r["band"] for r in rob.robustness(IMG, dets)}
    assert out == {"original": "strong", "jpeg": "strong", "resize": "uncertain", "screenshot": "strong"}
    # resize: weak 2 + strong 1 → strong·weak 공존 규칙 ①로 uncertain


def test_single_model_uses_its_own_band():
    out = rob.robustness(IMG, loaded(Fake("a", {200: 0.1})))
    assert {r["variant"]: r["band"] for r in out}["resize"] == "weak"
    assert out[0]["band"] == "strong"  # overall 규칙이면 모델 1개는 항상 uncertain


def test_original_bands_are_reused_not_rescored():
    a = loaded(Fake("a"))[0]
    out = rob.robustness(IMG, [a], original_bands={"a": "weak", "b": "strong"})
    assert out[0] == {"variant": "original", "band": "weak"}
    assert len(a.seen) == 3  # 원본은 추론하지 않고 변형 3개만


def test_original_bands_must_cover_detectors():
    with pytest.raises(ValueError):
        rob.robustness(IMG, loaded(Fake("a"), Fake("b")), original_bands={"a": "weak"})


def test_input_image_is_not_modified():
    img = IMG.copy()
    rob.robustness(img, loaded(Fake("a")))
    assert img.size == IMG.size and img.tobytes() == IMG.tobytes()
