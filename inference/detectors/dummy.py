"""테스트용 Detector. 고정 점수를 반환한다 (모델 없이 banding·main 테스트용)."""
from __future__ import annotations

from PIL import Image

from .base import Detector


class DummyDetector(Detector):
    """``DummyDetector("univfd", 0.9)``처럼 이름과 고정 점수를 받는다.

    score는 검사하지 않고 그대로 저장한다. 범위 밖 값을 넣으면 score() 호출 시
    ScoreRangeError가 나므로 계약 테스트에도 쓸 수 있다.
    """

    def __init__(self, name: str = "dummy", score: float = 0.5) -> None:
        super().__init__()
        self.name = name
        self.fixed_score = score
        self.calls = 0

    def _load(self) -> None:
        pass

    def _score(self, img: Image.Image) -> float:
        self.calls += 1
        return self.fixed_score
