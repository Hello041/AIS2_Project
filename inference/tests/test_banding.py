"""banding 단위 테스트 (계획서 §5.2, §5.3 단계 0). 모델 가중치 없이 돈다.

테스트 위치는 임시(inference/tests/). 팀 확정 전 — CLAUDE.md 미결 사항.
"""
import itertools
import math

import pytest
from PIL import Image

import banding
from banding import STRONG, UNCERTAIN, WEAK, ThresholdError, band, load_thresholds, overall
from detectors import ScoreRangeError
from detectors.dummy import DummyDetector

# 활성 모델 (2026-11-11 팀 결정: NPR 제거, UnivFD·AIDE·B-Free). 서버 기본 모델과 같아야 한다.
ACTIVE = ("univfd", "aide", "bfree")
# 테스트 전용 경계값. 실제 thresholds.yaml 값(B6에서 바뀔 수 있음)과 분리해 기대값이 흔들리지 않게 한다.
T = {name: (0.3, 0.7) for name in ACTIVE}


@pytest.fixture
def no_ensemble(tmp_path):
    """ensemble.yaml이 없는 경로 (실제 inference/ensemble.yaml 유무와 무관하게)."""
    return tmp_path / "ensemble.yaml"


def rule(bands, no_ensemble):
    return overall(dict(zip(ACTIVE, bands)), ensemble_path=no_ensemble)


# ---------------------------------------------------------------- thresholds.yaml
def test_repo_thresholds_cover_exactly_active_models():
    """실제 파일에는 활성 모델 3개만 있어야 한다(NPR 없음). 값은 검사하지 않는다(B6에서 바뀜)."""
    assert set(load_thresholds()) == set(ACTIVE)
    assert "npr" not in load_thresholds()


def test_repo_thresholds_are_valid_ranges():
    for name, (low, high) in load_thresholds().items():
        assert 0.0 <= low <= high <= 1.0, name


def write(tmp_path, text):
    p = tmp_path / "thresholds.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_thresholds_custom(tmp_path):
    p = write(tmp_path, "univfd: { low: 0.2, high: 0.9 }\nbfree: { low: 0.5, high: 0.5 }\n")
    assert load_thresholds(p) == {"univfd": (0.2, 0.9), "bfree": (0.5, 0.5)}


@pytest.mark.parametrize("text", [
    "univfd: { low: 0.8, high: 0.2 }",           # low > high
    "univfd: { low: -0.1, high: 0.7 }",          # 범위 밖
    "univfd: { low: 0.3, high: 1.5 }",
    "univfd: { low: 0.3 }",                      # high 없음
    "univfd: { low: 0.3, high: 0.7, mid: 0.5 }", # 모르는 키
    "univfd: { low: '0.3', high: 0.7 }",         # 문자열
    "univfd: 0.5",
    "- univfd",                                   # 매핑이 아님
])
def test_load_thresholds_rejects_invalid(tmp_path, text):
    with pytest.raises(ThresholdError):
        load_thresholds(write(tmp_path, text))


# ---------------------------------------------------------------- band
@pytest.mark.parametrize("score, expected", [
    (0.0, WEAK),
    (0.1, WEAK),
    (0.2999999, WEAK),
    (0.3, UNCERTAIN),      # low와 같으면 uncertain
    (0.5, UNCERTAIN),
    (0.7, UNCERTAIN),      # high와 같으면 uncertain
    (0.7000001, STRONG),
    (0.9, STRONG),
    (1.0, STRONG),
])
def test_band_boundaries(score, expected):
    assert band("univfd", score, T) == expected


def test_band_uses_per_model_thresholds():
    t = {"univfd": (0.3, 0.7), "bfree": (0.6, 0.95)}
    assert band("univfd", 0.8, t) == STRONG
    assert band("bfree", 0.8, t) == UNCERTAIN
    assert band("bfree", 0.5, t) == WEAK


def test_band_low_equals_high():
    t = {"m": (0.5, 0.5)}
    assert [band("m", s, t) for s in (0.49, 0.5, 0.51)] == [WEAK, UNCERTAIN, STRONG]


@pytest.mark.parametrize("name", ACTIVE)
def test_band_defaults_to_repo_file(name):
    """thresholds 인자를 생략하면 실제 파일 값을 쓴다. 값이 바뀌어도 깨지지 않게 파일에서 읽은 값과 비교."""
    repo = load_thresholds()
    low, high = repo[name]
    for s in sorted({0.0, low / 2, low, (low + high) / 2, high, (high + 1) / 2, 1.0}):
        assert band(name, s) == band(name, s, repo)


def test_band_removed_npr_is_not_active():
    with pytest.raises(ThresholdError):
        band("npr", 0.5)


def test_band_unknown_model_raises():
    with pytest.raises(ThresholdError):
        band("unknown", 0.5, T)


@pytest.mark.parametrize("bad", [-0.01, 1.01, math.nan, "0.5", None])
def test_band_rejects_bad_score(bad):
    with pytest.raises(ScoreRangeError):
        band("univfd", bad, T)


# ---------------------------------------------------------------- overall: 모델 3개
@pytest.mark.parametrize("b", [WEAK, UNCERTAIN, STRONG])
def test_three_all_same(b, no_ensemble):
    assert rule([b, b, b], no_ensemble) == (b, "rule")


@pytest.mark.parametrize("bands, expected", [
    # 규칙 ②: 2개 이상 나온 구간 (strong·weak가 함께 없는 2:1 조합 전부)
    ([WEAK, WEAK, UNCERTAIN], WEAK),
    ([UNCERTAIN, UNCERTAIN, WEAK], UNCERTAIN),
    ([STRONG, STRONG, UNCERTAIN], STRONG),
    ([UNCERTAIN, UNCERTAIN, STRONG], UNCERTAIN),
    # 규칙 ①: strong과 weak가 함께 있으면 uncertain (다수결이 strong·weak여도)
    ([STRONG, STRONG, WEAK], UNCERTAIN),
    ([WEAK, WEAK, STRONG], UNCERTAIN),
])
def test_three_two_to_one(bands, expected, no_ensemble):
    # 같은 조합을 모델 순서만 바꿔도 결과가 같아야 한다
    for perm in set(itertools.permutations(bands)):
        assert rule(list(perm), no_ensemble) == (expected, "rule")


def test_three_all_different(no_ensemble):
    # 규칙 ③(셋 다 다르면 uncertain)은 규칙 ①에 포함된다: 셋이 모두 다르면 weak·strong이
    # 반드시 함께 있으므로 ①에서 uncertain이 된다. 별도 분기 없이 이 테스트로만 확인한다.
    for perm in itertools.permutations([WEAK, UNCERTAIN, STRONG]):
        assert rule(list(perm), no_ensemble) == (UNCERTAIN, "rule")


def test_three_never_strong_with_weak(no_ensemble):
    """FPR 우선: weak가 하나라도 있으면 종합이 strong이 되지 않는다 (27개 조합 전수)."""
    for combo in itertools.product([WEAK, UNCERTAIN, STRONG], repeat=3):
        result, _ = rule(list(combo), no_ensemble)
        if WEAK in combo and STRONG in combo:
            assert result == UNCERTAIN
        if WEAK in combo:
            assert result != STRONG
        if STRONG in combo:
            assert result != WEAK


# ---------------------------------------------------------------- overall: 모델 2개·1개·0개
@pytest.mark.parametrize("b", [WEAK, UNCERTAIN, STRONG])
def test_two_same(b, no_ensemble):
    assert overall({"univfd": b, "bfree": b}, ensemble_path=no_ensemble) == (b, "rule")


@pytest.mark.parametrize("a, b", [(WEAK, STRONG), (WEAK, UNCERTAIN), (STRONG, UNCERTAIN)])
def test_two_different(a, b, no_ensemble):
    # 모델 2개에서 서로 다르면 1:1 동률 → 과반수 없음 → uncertain
    assert overall({"univfd": a, "bfree": b}, ensemble_path=no_ensemble) == (UNCERTAIN, "rule")
    assert overall({"univfd": b, "bfree": a}, ensemble_path=no_ensemble) == (UNCERTAIN, "rule")


@pytest.mark.parametrize("bands", [{}, {"univfd": STRONG}, {"bfree": WEAK}])
def test_zero_or_one_model_is_uncertain(bands, no_ensemble):
    assert overall(bands, ensemble_path=no_ensemble) == (UNCERTAIN, "rule")


# ---------------------------------------------------------------- overall: 모델 4개 이상 (일반화 규칙, 팀 결정 2026-11-04)
def many(bands, no_ensemble):
    return overall({f"m{i}": b for i, b in enumerate(bands)}, ensemble_path=no_ensemble)


@pytest.mark.parametrize("bands, expected", [
    # 1. strong·weak 공존 → uncertain (과반수가 strong이어도)
    ([STRONG, STRONG, STRONG, WEAK], UNCERTAIN),
    ([WEAK, WEAK, WEAK, STRONG], UNCERTAIN),
    ([STRONG, WEAK, UNCERTAIN, UNCERTAIN], UNCERTAIN),
    # 2. 과반수(50% 초과)
    ([STRONG, STRONG, STRONG, STRONG], STRONG),
    ([STRONG, STRONG, STRONG, UNCERTAIN], STRONG),          # 3/4
    ([WEAK, WEAK, WEAK, UNCERTAIN], WEAK),
    ([UNCERTAIN, UNCERTAIN, UNCERTAIN, WEAK], UNCERTAIN),
    # 3. 동률(정확히 50%)은 과반수가 아님 → uncertain
    ([STRONG, STRONG, UNCERTAIN, UNCERTAIN], UNCERTAIN),
    ([WEAK, WEAK, UNCERTAIN, UNCERTAIN], UNCERTAIN),
])
def test_four_models(bands, expected, no_ensemble):
    for perm in set(itertools.permutations(bands)):
        assert many(list(perm), no_ensemble) == (expected, "rule")


@pytest.mark.parametrize("bands, expected", [
    ([STRONG] * 3 + [UNCERTAIN] * 2, STRONG),               # 3/5
    ([WEAK] * 3 + [UNCERTAIN] * 2, WEAK),
    ([UNCERTAIN] * 3 + [STRONG] * 2, UNCERTAIN),
    ([STRONG] * 4 + [WEAK], UNCERTAIN),                     # 공존
    ([STRONG] * 3 + [UNCERTAIN] * 3, UNCERTAIN),            # 6개 동률
    ([STRONG] * 4 + [UNCERTAIN] * 2, STRONG),               # 4/6
    ([WEAK] * 4 + [UNCERTAIN] * 3, WEAK),                   # 4/7
    ([WEAK] * 3 + [UNCERTAIN] * 4, UNCERTAIN),              # 4/7 uncertain
    ([STRONG] * 5 + [UNCERTAIN] * 5, UNCERTAIN),            # 10개 동률
])
def test_five_or_more_models(bands, expected, no_ensemble):
    assert many(bands, no_ensemble) == (expected, "rule")
    assert many(bands[::-1], no_ensemble) == (expected, "rule")


def spec_rule(bands):
    """§5.3 문구를 그대로 옮긴 기준 구현 (모델 0~3개). 일반화 규칙과 비교하는 용도."""
    if len(bands) <= 1:
        return UNCERTAIN                                      # 팀 결정
    if len(bands) == 2:
        return bands[0] if bands[0] == bands[1] else UNCERTAIN
    if STRONG in bands and WEAK in bands:                     # ①
        return UNCERTAIN
    if len(set(bands)) == 3:                                  # ③
        return UNCERTAIN
    return next(b for b in BANDS3 if bands.count(b) >= 2)     # ② 2개 이상 나온 구간


BANDS3 = [WEAK, UNCERTAIN, STRONG]


@pytest.mark.parametrize("n", [0, 1, 2, 3])
def test_general_rule_matches_plan_for_up_to_three(n, no_ensemble):
    """일반화 규칙이 모델 0~3개에서 기존 규칙과 결과가 같다 (1+3+9+27개 조합 전수)."""
    for combo in itertools.product(BANDS3, repeat=n):
        assert many(list(combo), no_ensemble) == (spec_rule(list(combo)), "rule"), combo


@pytest.mark.parametrize("n", range(2, 8))
def test_general_rule_properties(n, no_ensemble):
    """모델 2~7개 전수: FPR 우선 성질과 과반수 조건."""
    for combo in itertools.product(BANDS3, repeat=n):
        result, _ = many(list(combo), no_ensemble)
        if STRONG in combo and WEAK in combo:
            assert result == UNCERTAIN
        if WEAK in combo:
            assert result != STRONG
        if STRONG in combo:
            assert result != WEAK
        if result != UNCERTAIN:
            assert combo.count(result) * 2 > n


# ---------------------------------------------------------------- overall: 예외

@pytest.mark.parametrize("bad", ["Strong", "high", "", None, 0.9])
def test_unknown_band_raises(bad, no_ensemble):
    with pytest.raises(ValueError, match="알 수 없는 구간"):
        overall({"univfd": STRONG, "bfree": bad}, ensemble_path=no_ensemble)


def test_ensemble_file_present_is_not_silently_ignored(tmp_path):
    p = tmp_path / "ensemble.yaml"
    p.write_text("bands: {low: 0.3, high: 0.7}\n", encoding="utf-8")
    with pytest.raises(NotImplementedError):
        overall({"univfd": WEAK, "aide": WEAK, "bfree": WEAK}, ensemble_path=p)


def test_default_ensemble_path_is_next_to_banding():
    assert banding.ENSEMBLE_PATH.parent == banding.THRESHOLDS_PATH.parent


# ---------------------------------------------------------------- overall: 활성 모델 3개의 주요 조합
@pytest.mark.parametrize("bands, expected", [
    ([STRONG, STRONG, STRONG], STRONG),          # 전원 AI 쪽
    ([WEAK, WEAK, WEAK], WEAK),                  # 전원 실제 쪽
    ([UNCERTAIN, UNCERTAIN, UNCERTAIN], UNCERTAIN),
    ([STRONG, STRONG, UNCERTAIN], STRONG),       # 일부 모델 uncertain, 과반수 strong
    ([WEAK, UNCERTAIN, WEAK], WEAK),             # 일부 모델 uncertain, 과반수 weak
    ([UNCERTAIN, STRONG, UNCERTAIN], UNCERTAIN), # 과반수가 uncertain
    ([STRONG, STRONG, WEAK], UNCERTAIN),         # strong·weak 공존 → 과반수여도 uncertain (FPR 우선)
    ([WEAK, STRONG, UNCERTAIN], UNCERTAIN),      # 셋 다 다름
])
def test_active_models_main_cases(bands, expected, no_ensemble):
    assert overall(dict(zip(ACTIVE, bands)), ensemble_path=no_ensemble) == (expected, "rule")


# ---------------------------------------------------------------- 모의 Detector → band → overall
@pytest.mark.parametrize("scores, bands, expected", [
    ({"univfd": 0.1, "aide": 0.2, "bfree": 0.05}, [WEAK, WEAK, WEAK], WEAK),
    ({"univfd": 0.52, "aide": 0.81, "bfree": 0.12}, [UNCERTAIN, STRONG, WEAK], UNCERTAIN),  # §5.4 예시
    ({"univfd": 0.9, "aide": 0.95, "bfree": 0.5}, [STRONG, STRONG, UNCERTAIN], STRONG),
    ({"univfd": 0.3, "aide": 0.7, "bfree": 0.71}, [UNCERTAIN, UNCERTAIN, STRONG], UNCERTAIN),
    ({"univfd": 0.99, "aide": 0.99, "bfree": 0.01}, [STRONG, STRONG, WEAK], UNCERTAIN),
])
def test_mock_detectors_end_to_end(scores, bands, expected, no_ensemble):
    """Detector.score → band → overall. 경계값은 테스트용 T(0.3/0.7)를 넘겨 실제 파일 값과 분리한다."""
    img = Image.new("RGB", (32, 32))
    detectors = [DummyDetector(name, s) for name, s in scores.items()]
    for d in detectors:
        d.load()
    raw = {d.name: d.score(img) for d in detectors}
    got = {name: band(name, s, T) for name, s in raw.items()}
    assert list(got.values()) == bands
    assert overall(got, raw, ensemble_path=no_ensemble) == (expected, "rule")
