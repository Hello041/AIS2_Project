"""Detector 인터페이스 (계획서 §5.1).

모델 하나 = detectors/ 아래 모듈 하나. 각 모듈은 Detector를 상속한 클래스를 하나 정의한다.
main.py와 banding.py는 이 인터페이스만 알고, 모델 내부는 모른다.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod

from PIL import Image


class ScoreRangeError(ValueError):
    """원점수가 [0, 1] 밖이거나 숫자가 아닐 때."""


def to_rgb(img: Image.Image) -> Image.Image:
    """모든 입력을 RGB로 맞춘다. RGBA·P(팔레트)·L(흑백)·CMYK 등을 처리한다.

    투명 영역은 흰색 배경 위에 합성한다(검은색으로 바뀌어 점수가 흔들리는 것을 막기 위해).
    """
    if img.mode == "RGB":
        return img
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return img.convert("RGB")


def check_score(value: object, name: str = "?") -> float:
    """원점수를 float로 바꾸고 [0, 1] 범위인지 검사한다. 벗어나면 ScoreRangeError.

    잘라내지(clamp) 않는다. 범위 밖 값은 Detector 구현의 버그이므로 숨기지 않고 드러낸다.
    """
    if isinstance(value, (bool, str, bytes)):
        raise ScoreRangeError(f"[{name}] 원점수가 숫자가 아닙니다: {value!r}")
    try:
        score = float(value)  # numpy float, 0-dim tensor도 허용
    except (TypeError, ValueError):
        raise ScoreRangeError(f"[{name}] 원점수를 float로 바꿀 수 없습니다: {value!r}") from None
    if math.isnan(score) or not 0.0 <= score <= 1.0:
        raise ScoreRangeError(f"[{name}] 원점수가 [0, 1] 밖입니다: {score!r}")
    return score


class Detector(ABC):
    """AI 생성 이미지 탐지 모델의 공통 인터페이스.

    계약
    ----
    - ``score(img)``는 **0~1 원점수**를 반환한다. **클수록 AI 생성 쪽**이다.
    - 원점수는 **확률이 아니다.** 모델마다 분포가 다르며, 구간 판정은 thresholds.yaml의
      모델별 경계값(banding.py)으로 한다. 로짓을 내는 모델은 sigmoid/softmax로 0~1에 맞춘다.
    - ``load()``는 서버 시작 시 한 번만 호출한다. 요청마다 다시 로드하지 않는다.
    - 추론은 torch.inference_mode(), 배치 1, CPU.

    구현 방법
    --------
    하위 클래스는 ``name``을 정하고 ``load()``와 ``_score(img)``를 구현한다.
    ``score()``는 이 클래스가 제공하며 RGB 변환 → ``_score`` → 범위 검사를 한다.
    ``_score``는 RGB 이미지만 받는다고 가정해도 된다.
    """

    name: str = ""
    # 클래스 속성: 하위 클래스가 __init__에서 super().__init__()을 빠뜨려도 동작하게
    _loaded: bool = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        """가중치를 메모리에 올린다. 하위 클래스는 _load()를 구현한다. 두 번째 호출은 무시."""
        if self._loaded:
            return
        self._load()
        self._loaded = True

    def score(self, img: Image.Image) -> float:
        """0~1 원점수. 클수록 AI 생성 쪽. 확률이 아님."""
        if not self._loaded:
            raise RuntimeError(f"[{self.name}] load()를 먼저 호출해야 합니다")
        return check_score(self._score(to_rgb(img)), self.name)

    @abstractmethod
    def _load(self) -> None:
        """가중치 로드. load()가 한 번만 부른다."""

    @abstractmethod
    def _score(self, img: Image.Image) -> float:
        """RGB 이미지 → 원점수. 범위 검사는 score()가 한다."""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r} loaded={self._loaded}>"
