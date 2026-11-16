"""판정 안정성 (계획서 §12.4): 원본과 변형 3개(JPEG·Resize·Screenshot)의 종합 구간을 비교한다.

    robustness(img, detectors, original_bands=None) -> [{"variant": "original", "band": ...}, ...]

- 변형은 검증 데이터와 같은 함수(variants.make_variant)로 메모리에서만 만든다.
- 모델이 2개 이상이면 버전마다 banding.overall()로 종합 구간을 낸다(서버 본 판정과 같은 규칙).
- 모델이 1개면(시간 때문에 가벼운 모델만 쓸 때, §12.4) 그 모델의 구간을 그대로 쓴다.
  banding의 규칙은 모델 1개를 항상 uncertain으로 보므로 overall을 거치지 않는다.
- original_bands를 주면 원본은 다시 추론하지 않는다(본 분석 결과 재사용). 단, detectors와 모델이 같아야 한다.
- 응답의 variant 이름은 계획서 §12.6 예시를 따른다: original, jpeg, resize, screenshot.
"""
from __future__ import annotations

from PIL import Image

import banding
import variants
from detectors import Detector

# variants.VERSIONS → 응답 이름 (§12.6)
VARIANT_NAMES = {"jpeg70": "jpeg", "resize50": "resize", "screenshot": "screenshot"}


def _bands(img: Image.Image, detectors: list[Detector]) -> dict[str, str]:
    return {d.name: banding.band(d.name, d.score(img)) for d in detectors}


def _summary_band(bands: dict[str, str]) -> str:
    if len(bands) == 1:
        return next(iter(bands.values()))
    return banding.overall(bands)[0]


def robustness(img: Image.Image, detectors: list[Detector],
               original_bands: dict[str, str] | None = None) -> list[dict]:
    if not detectors:
        raise ValueError("detectors가 비어 있습니다")
    names = {d.name for d in detectors}
    if original_bands is not None:
        original_bands = {k: v for k, v in original_bands.items() if k in names}
        if set(original_bands) != names:
            raise ValueError(f"original_bands에 {sorted(names - set(original_bands))} 결과가 없습니다")
    else:
        original_bands = _bands(img, detectors)

    out = [{"variant": "original", "band": _summary_band(original_bands)}]
    for version in variants.VERSIONS:
        variant = variants.make_variant(img, version)
        try:
            out.append({"variant": VARIANT_NAMES[version], "band": _summary_band(_bands(variant, detectors))})
        finally:
            variant.close()
    return out
