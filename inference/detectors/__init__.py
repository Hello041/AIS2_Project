"""Detector 레지스트리.

모듈 이름 = 모델 이름: ``detectors/<name>.py``에 Detector 하위 클래스를 하나 정의하면
``create_detectors(["<name>"])``로 만들 수 있다. 모델을 추가할 때 이 파일은 고치지 않는다.

활성 모델은 환경 변수 ``DETECTORS``(예: ``"univfd,bfree"``)로 고른다. 없으면 DEFAULT_DETECTORS.
"""
from __future__ import annotations

import importlib
import inspect
import os
import re

from .base import Detector, ScoreRangeError, check_score, to_rgb

__all__ = [
    "Detector", "ScoreRangeError", "check_score", "to_rgb",
    "DEFAULT_DETECTORS", "active_names", "get_detector_class", "create_detectors",
]

DEFAULT_DETECTORS = ("univfd", "aide", "bfree")  # 2026-11-10 NPR → B-Free (계획서 §7 '11/10 점검 결과')
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def active_names(env: str | None = None) -> list[str]:
    """DETECTORS 환경 변수(또는 env 인자)를 이름 목록으로. 공백·대소문자·빈 항목은 정리, 중복은 오류."""
    raw = os.environ.get("DETECTORS") if env is None else env
    if raw is None or not raw.strip():
        return list(DEFAULT_DETECTORS)
    names = [n.strip().lower() for n in raw.split(",") if n.strip()]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise ValueError(f"DETECTORS에 중복된 이름: {', '.join(dup)}")
    return names


def get_detector_class(name: str) -> type[Detector]:
    """detectors/<name>.py에서 정의된 Detector 하위 클래스를 찾는다."""
    if not _NAME.match(name) or name in ("base",):
        raise ValueError(f"잘못된 detector 이름: {name!r}")
    try:
        module = importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError as e:
        if e.name == f"{__name__}.{name}":
            raise ValueError(f"detector 모듈이 없습니다: detectors/{name}.py") from None
        raise
    classes = [
        obj for obj in vars(module).values()
        if inspect.isclass(obj) and issubclass(obj, Detector)
        and obj.__module__ == module.__name__ and not inspect.isabstract(obj)
    ]
    if len(classes) != 1:
        raise ValueError(
            f"detectors/{name}.py에는 Detector 하위 클래스가 정확히 하나 있어야 합니다 (찾은 수: {len(classes)})"
        )
    return classes[0]


def create_detectors(names: list[str] | None = None, *, load: bool = False) -> list[Detector]:
    """이름 목록(없으면 active_names())으로 Detector 인스턴스를 만든다. load=True면 load()까지."""
    names = active_names() if names is None else names
    detectors = []
    for name in names:
        det = get_detector_class(name)()
        if det.name != name:
            raise ValueError(f"detectors/{name}.py의 클래스 name이 {det.name!r}입니다 ({name!r}이어야 함)")
        detectors.append(det)
    if load:
        for det in detectors:
            det.load()
    return detectors
