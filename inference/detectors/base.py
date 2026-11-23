"""Detector 인터페이스 (계획서 §5.1).

모델 하나 = detectors/ 아래 모듈 하나. 각 모듈은 Detector를 상속한 클래스를 하나 정의한다.
main.py와 banding.py는 이 인터페이스만 알고, 모델 내부는 모른다.
"""
from __future__ import annotations

import logging
import math
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from PIL import Image

log = logging.getLogger("inference")


class ScoreRangeError(ValueError):
    """원점수가 [0, 1] 밖이거나 숫자가 아닐 때."""


def to_rgb(img: Image.Image) -> Image.Image:
    """모든 입력을 RGB로 맞춘다. RGBA·P(팔레트)·L(흑백)·CMYK 등을 처리한다.

    투명 영역은 흰색 배경 위에 합성한다(검은색으로 바뀌어 점수가 흔들리는 것을 막기 위해).
    16비트 흑백(PNG → I;16 또는 I)은 0~65535를 0~255로 줄인다. Pillow의 convert("RGB")는
    255를 넘는 값을 잘라내 거의 흰 이미지가 된다.
    """
    if img.mode == "RGB":
        return img
    if img.mode.startswith("I;16") or img.mode == "I":
        arr = np.asarray(img, dtype=np.float64)
        if img.mode.startswith("I;16") or arr.max() > 255:  # I 모드는 8비트 범위 값일 수도 있다
            arr = arr / 257.0
        return Image.fromarray(np.clip(np.rint(arr), 0, 255).astype(np.uint8), "L").convert("RGB")
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


# ---------------------------------------------------------------- 추론 장치 (CPU / GPU)
DEVICE_ENV = "DEVICE"
_DEVICE = re.compile(r"^(auto|cpu|cuda(:\d+)?)$")
_cuda_configured = False


def resolve_device(name: str = "", env: dict | None = None) -> str:
    """모델 ``name``을 올릴 장치 문자열("cpu", "cuda", "cuda:1" …).

    환경 변수 ``DEVICE_<NAME>``(예: DEVICE_AIDE)이 있으면 그 값, 없으면 ``DEVICE``, 둘 다 없으면 "auto".
    - auto: GPU를 쓸 수 있으면 "cuda", 없으면 "cpu" (경고 로그)
    - cuda / cuda:N: GPU 필수. 쓸 수 없으면 시작 시 RuntimeError (GPU 배포에서는 이 값을 쓴다)
    - cpu: 항상 CPU
    """
    env = os.environ if env is None else env
    raw = env.get(f"{DEVICE_ENV}_{name.upper()}") if name else None
    if raw is None or not raw.strip():
        raw = env.get(DEVICE_ENV)
    value = (raw or "auto").strip().lower()
    if not _DEVICE.match(value):
        raise ValueError(f"DEVICE 값은 auto, cpu, cuda, cuda:N 중 하나여야 합니다: {raw!r}")
    if value == "cpu":
        return "cpu"

    import torch
    available = torch.cuda.is_available()
    if value == "auto":
        if not available:
            log.warning("[%s] GPU를 쓸 수 없어 CPU로 실행합니다 (DEVICE=auto)", name or "?")
            return "cpu"
        value = "cuda"
    elif not available:
        raise RuntimeError(
            f"[{name or '?'}] {value}를 요청했지만 GPU를 쓸 수 없습니다. "
            "CUDA용 torch가 설치됐는지 확인하세요 (inference/README.md 'GPU 실행')."
        )
    index = int(value.split(":")[1]) if ":" in value else 0
    if index >= torch.cuda.device_count():
        raise RuntimeError(f"[{name or '?'}] {value}가 없습니다 (GPU {torch.cuda.device_count()}개)")
    configure_cuda()
    return value


def configure_cuda() -> None:
    """GPU 점수가 CPU 점수(경계값의 기준)와 최대한 같도록 정밀도를 고정한다. 한 번만 적용.

    - TF32 끔: Ampere 이상 GPU는 기본으로 행렬곱을 TF32(정밀도 낮음)로 바꿀 수 있다.
    - 결정적 알고리즘: 같은 입력이면 매번 비트 단위로 같은 점수 (2026-11-23 결정).
      이것이 없으면 GPU에서 같은 이미지의 점수가 실행마다 1e-7 정도 흔들린다. B-Free 약 25% 느려짐(MX450 3.7→4.6초).
      cuBLAS 결정적 모드에는 CUBLAS_WORKSPACE_CONFIG가 첫 GPU 행렬곱 전에 있어야 한다(이미 있으면 그 값을 쓴다).
      결정적 구현이 없는 연산은 오류 대신 경고만 낸다(warn_only) — 서비스가 멈추지 않게.
      warn_only에서는 비결정적인 Memory-Efficient·Flash 어텐션(scaled_dot_product_attention)이 경고만 내고
      그대로 쓰이므로 직접 꺼서 결정적인 기본(math) 경로를 쓰게 한다 (ViT인 CommFor·B-Free가 해당).
    FP16·autocast는 쓰지 않는다(점수가 달라짐).
    """
    global _cuda_configured
    if _cuda_configured:
        return
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    _cuda_configured = True


@dataclass
class Explanation:
    """모델 주목 영역 (히트맵 원자료). 판정과 무관한 참고 정보다.

    - ``values``: 이미지를 ``cell``×``cell`` 픽셀 칸으로 나눈 격자(행, 열)의 주목도. 클수록 더 주목.
      모델이 **보지 않은 칸은 NaN**이다(분석 범위 밖). 격자 밖(오른쪽·아래 자투리)도 범위 밖이다.
    - ``cell``: 격자 한 칸의 픽셀 크기. 좌표는 디코딩된 이미지의 저장 방향(EXIF 회전 적용 전) 기준.
    - ``method``: 계산 방법 이름 (예: "attention_rollout").
    """

    values: np.ndarray
    cell: int
    method: str


class Detector(ABC):
    """AI 생성 이미지 탐지 모델의 공통 인터페이스.

    계약
    ----
    - ``score(img)``는 **0~1 원점수**를 반환한다. **클수록 AI 생성 쪽**이다.
    - 원점수는 **확률이 아니다.** 모델마다 분포가 다르며, 구간 판정은 thresholds.yaml의
      모델별 경계값(banding.py)으로 한다. 로짓을 내는 모델은 sigmoid/softmax로 0~1에 맞춘다.
    - ``load()``는 서버 시작 시 한 번만 호출한다. 요청마다 다시 로드하지 않는다.
    - 추론은 torch.inference_mode(), 배치 1, FP32. 장치는 ``self.device``(DEVICE 환경 변수, resolve_device).
      전처리는 CPU에서 하고 모델 입력 텐서만 ``self.device``로 옮긴다 (CPU 검증 결과와 같은 전처리 유지).

    구현 방법
    --------
    하위 클래스는 ``name``을 정하고 ``load()``와 ``_score(img)``를 구현한다.
    ``score()``는 이 클래스가 제공하며 RGB 변환 → ``_score`` → 범위 검사를 한다.
    ``_score``는 RGB 이미지만 받는다고 가정해도 된다.
    """

    name: str = ""
    # 클래스 속성: 하위 클래스가 __init__에서 super().__init__()을 빠뜨려도 동작하게
    _loaded: bool = False
    #: 모델을 올린 장치. load()가 resolve_device()로 정한다. _load()에서 모델을 이 장치로 옮긴다.
    device: str = "cpu"

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        """가중치를 메모리에 올린다. 하위 클래스는 _load()를 구현한다. 두 번째 호출은 무시."""
        if self._loaded:
            return
        self.device = resolve_device(self.name)
        self._load()
        self._loaded = True
        log.info("[%s] loaded on %s", self.name, self.device)

    def score(self, img: Image.Image) -> float:
        """0~1 원점수. 클수록 AI 생성 쪽. 확률이 아님."""
        if not self._loaded:
            raise RuntimeError(f"[{self.name}] load()를 먼저 호출해야 합니다")
        return check_score(self._score(to_rgb(img)), self.name)

    # ---------------------------------------------------------------- 히트맵 (선택 기능)
    #: 히트맵을 만들 수 있는 모델만 True. main.py는 이 값과 HEATMAP_MODEL로 대상을 고른다.
    supports_explanation: bool = False

    def score_and_explain(self, img: Image.Image) -> tuple[float, Explanation | None]:
        """원점수와 주목 영역을 **같은 추론 한 번**으로 얻는다.

        원점수는 ``score()``와 같아야 한다(주목 영역 수집이 판정에 영향을 주면 안 된다).
        주목 영역 계산이 실패하면 예외 대신 ``None``을 돌려준다 — 판정은 그대로 진행돼야 하므로.
        지원하지 않는 모델은 ``(score(img), None)``.
        """
        if not self._loaded:
            raise RuntimeError(f"[{self.name}] load()를 먼저 호출해야 합니다")
        rgb = to_rgb(img)
        if not self.supports_explanation:
            return check_score(self._score(rgb), self.name), None
        score, explanation = self._score_and_explain(rgb)
        return check_score(score, self.name), explanation

    def _score_and_explain(self, img: Image.Image) -> tuple[float, Explanation | None]:
        """하위 클래스가 supports_explanation=True일 때 구현한다. RGB 이미지만 받는다."""
        return self._score(img), None

    @abstractmethod
    def _load(self) -> None:
        """가중치 로드. load()가 한 번만 부른다."""

    @abstractmethod
    def _score(self, img: Image.Image) -> float:
        """RGB 이미지 → 원점수. 범위 검사는 score()가 한다."""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r} loaded={self._loaded}>"
