"""원점수 → 구간, 종합 판정 (계획서 §5.2, §5.3).

판정 로직은 이 파일에만 둔다. 모델을 추가·교체·제거해도 이 파일은 고치지 않는다(§5.1).
모델 이름은 thresholds.yaml에서만 읽고, 규칙 방식은 모델 수와 무관하게 동작한다.

- ``band(name, score)``: thresholds.yaml의 모델별 경계값으로 weak / uncertain / strong.
- ``overall(bands, scores)``: 종합 판정. ensemble.yaml이 있으면 스태킹(단계 1, C3에서 구현),
  없으면 규칙 방식(단계 0). 판단이 애매하면 항상 uncertain 쪽으로 기운다(FPR 우선).
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path

import yaml

from detectors.base import check_score

WEAK, UNCERTAIN, STRONG = "weak", "uncertain", "strong"
BANDS = (WEAK, UNCERTAIN, STRONG)

HERE = Path(__file__).resolve().parent
THRESHOLDS_PATH = HERE / "thresholds.yaml"
ENSEMBLE_PATH = HERE / "ensemble.yaml"


class ThresholdError(ValueError):
    """thresholds.yaml 형식이 잘못됐거나 모델의 경계값이 없을 때."""


@lru_cache(maxsize=None)
def load_thresholds(path: str | Path = THRESHOLDS_PATH) -> dict[str, tuple[float, float]]:
    """thresholds.yaml → {모델 이름: (low, high)}. 0 ≤ low ≤ high ≤ 1이 아니면 ThresholdError.

    서버 시작 시 한 번 읽고 캐시한다. 파일을 고치면 서버를 다시 시작한다.
    """
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ThresholdError(f"{path}: 최상위는 '모델 이름: {{low, high}}' 매핑이어야 합니다")
    thresholds = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict) or set(entry) != {"low", "high"}:
            raise ThresholdError(f"{path}: {name}에는 low와 high만 있어야 합니다: {entry!r}")
        try:
            low = check_score(entry["low"], f"{name}.low")
            high = check_score(entry["high"], f"{name}.high")
        except ValueError as e:
            raise ThresholdError(f"{path}: {e}") from None
        if low > high:
            raise ThresholdError(f"{path}: {name}의 low({low})가 high({high})보다 큽니다")
        thresholds[str(name)] = (low, high)
    return thresholds


def band(model_name: str, score: float, thresholds: dict[str, tuple[float, float]] | None = None) -> str:
    """원점수 → 구간. 경계값과 정확히 같으면 uncertain.

    thresholds를 주지 않으면 thresholds.yaml을 쓴다. 경계값이 없는 모델은 ThresholdError
    (기본값으로 판정하지 않는다). 원점수가 [0, 1] 밖이면 ScoreRangeError.
    """
    thresholds = load_thresholds() if thresholds is None else thresholds
    if model_name not in thresholds:
        raise ThresholdError(f"thresholds.yaml에 {model_name!r}의 경계값이 없습니다")
    low, high = thresholds[model_name]
    score = check_score(score, model_name)
    if score < low:
        return WEAK
    if score > high:
        return STRONG
    return UNCERTAIN


def overall(
    bands: dict[str, str],
    scores: dict[str, float] | None = None,
    *,
    ensemble_path: str | Path = ENSEMBLE_PATH,
) -> tuple[str, str]:
    """종합 판정 → (구간, 방식). 방식은 'rule' | 'stacking'.

    bands는 {모델 이름: 구간}. scores(원점수)는 스태킹에서만 쓴다.
    """
    for name, b in bands.items():
        if b not in BANDS:
            raise ValueError(f"[{name}] 알 수 없는 구간: {b!r}")
    if Path(ensemble_path).exists():
        # 단계 1(스태킹)은 C3에서 구현한다. 규칙 방식으로 조용히 돌아가면 응답의
        # overall_method가 실제 학습 결과와 달라지므로, 파일이 있는데 미구현이면 오류로 드러낸다.
        raise NotImplementedError(f"{ensemble_path}가 있지만 스태킹은 아직 구현되지 않았습니다 (C3)")
    return _rule(list(bands.values())), "rule"


def _rule(bands: list[str]) -> str:
    """단계 0 규칙 방식. §5.3(모델 2·3개)을 모델 수와 무관하게 일반화한 것 (팀 결정 2026-11-04).

    1. strong과 weak가 함께 있으면 uncertain (모델 판단이 정반대).
    2. 아니면 전체 모델의 과반수(50% 초과)를 차지하는 구간.
    3. 과반수 구간이 없으면(동률 등) uncertain.

    모델 3개: 2는 §5.3 ②(2개 이상 나온 구간)와 같다. §5.3 ③(셋 다 다름)은 1에 포함된다.
    모델 2개: 같으면 2/2로 그 구간, 다르면 1/1로 과반수가 없어 uncertain — §5.3과 같다.
    """
    n = len(bands)
    if n <= 1:
        # 모델이 0~1개면 교차 확인이 안 되므로 uncertain (팀 결정, docs/prompts/B_connect B2).
        # 이 분기가 없으면 1개일 때 1/1이 과반수가 되어 그 구간이 나온다.
        return UNCERTAIN
    if STRONG in bands and WEAK in bands:
        return UNCERTAIN
    top, count = Counter(bands).most_common(1)[0]
    return top if count * 2 > n else UNCERTAIN
