"""단계 1 앙상블(스태킹) 학습과 방식별 비교 (계획서 §5.3 단계 1, §12.4, 프롬프트 C2).

    python ml/fit_ensemble.py             # 비교표 → ml/reports/ensemble_compare.md, 파라미터 → ml/reports/ensemble.yaml
    python ml/fit_ensemble.py --install   # 채택 기준을 넘으면 inference/ensemble.yaml에도 복사

스태킹 (§5.3):
  1. 보정: 모델마다 Platt p_i = sigmoid(a_i · raw_i + b_i)
  2. 융합: 보정 점수 p_1..p_n으로 로지스틱 회귀 → 융합 점수 f
  3. 불일치: max(p) − min(p) > τ 이면 uncertain
  4. 구간: f < t_low → weak, f > t_high → strong, 나머지 uncertain

학습 부분에서만 맞추는 것 (검토 문서 6번): Platt, 로지스틱 회귀, t_high, t_low, τ.
  t_high: 학습 부분 실제 사진 중 strong 비율(FPR) ≤ 5%
  t_low:  학습 부분 AI 이미지 중 weak 비율 ≤ 5%  (t_high와 대칭. B6의 low 기준 'AI 대부분이 넘는 값'과 같은 취지)
  τ:      후보 0.3~0.9와 1.0(끔) 중 학습 부분에서 (맞은 판정 수 − 2 × 틀린 판정 수)가 가장 큰 값, 동점이면 작은 τ
교차검증: GroupKFold(source_id, 5-fold). 같은 원본의 변형은 같은 fold에 들어간다.

비교 대상:
  - 규칙: thresholds.yaml + banding 단계 0 규칙 (학습 없음. thresholds.yaml은 800장 전체로 정했으므로 약간 유리)
  - 스태킹, 스태킹(τ 끔)
  - 단순 평균: 원점수 평균, t_low·t_high는 스태킹과 같은 기준으로 fold마다
  - 모델별 단일: 원점수, t_low·t_high는 스태킹과 같은 기준으로 fold마다

inference/ensemble.yaml이 생기면 banding.overall()이 스태킹을 쓴다. C3(스태킹 분기) 전에는 서버가 500을 내므로
--install은 C3 이후에 쓴다.
"""
from __future__ import annotations

import argparse
import math
import shutil
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "inference"))

import banding  # noqa: E402
from detectors import active_names  # noqa: E402

SCORES = ROOT / "ml" / "scores.csv"
REPORTS = ROOT / "ml" / "reports"
INSTALL_PATH = ROOT / "inference" / "ensemble.yaml"

MAX_FPR = 0.05        # t_high: 실제 → strong 비율 상한
MAX_AI_WEAK = 0.05    # t_low:  AI → weak 비율 상한
TAUS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]   # 1.0 = 불일치 규칙 끔 (max−min은 1을 넘지 않음)
WRONG_PENALTY = 2     # τ 선택 점수 = 맞음 − 2 × 틀림 (FPR 우선)
N_SPLITS = 5
WEAK, UNCERTAIN, STRONG = banding.WEAK, banding.UNCERTAIN, banding.STRONG


# ---------------------------------------------------------------- 학습
def fit_platt(raw: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """p = sigmoid(a · raw + b). 정규화 없는 최대우도(Platt)."""
    lr = LogisticRegression(penalty=None, max_iter=1000).fit(raw.reshape(-1, 1), y)
    return float(lr.coef_[0, 0]), float(lr.intercept_[0])


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def calibrate(raw: np.ndarray, calib: list[tuple[float, float]]) -> np.ndarray:
    """raw (N, 모델 수) → 보정 점수 p (N, 모델 수)."""
    return np.column_stack([sigmoid(a * raw[:, i] + b) for i, (a, b) in enumerate(calib)])


def fit_thresholds(f: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """t_high: 실제 중 f > t_high 비율 ≤ MAX_FPR. t_low: AI 중 f < t_low 비율 ≤ MAX_AI_WEAK. t_low ≤ t_high."""
    real = np.sort(f[y == 0])[::-1]          # 큰 순
    ai = np.sort(f[y == 1])                  # 작은 순
    t_high = float(real[math.floor(MAX_FPR * len(real))])
    t_low = float(ai[math.floor(MAX_AI_WEAK * len(ai))])
    return min(t_low, t_high), t_high


def to_bands(f: np.ndarray, t_low: float, t_high: float, spread: np.ndarray | None = None,
             tau: float = 1.0) -> np.ndarray:
    out = np.where(f < t_low, WEAK, np.where(f > t_high, STRONG, UNCERTAIN)).astype(object)
    if spread is not None:
        out[spread > tau] = UNCERTAIN
    return out


def tau_score(bands: np.ndarray, y: np.ndarray) -> int:
    correct = np.sum((bands == WEAK) & (y == 0)) + np.sum((bands == STRONG) & (y == 1))
    wrong = np.sum((bands == STRONG) & (y == 0)) + np.sum((bands == WEAK) & (y == 1))
    return int(correct - WRONG_PENALTY * wrong)


def fit_stacking(raw: np.ndarray, y: np.ndarray, use_tau: bool = True) -> dict:
    calib = [fit_platt(raw[:, i], y) for i in range(raw.shape[1])]
    p = calibrate(raw, calib)
    lr = LogisticRegression(max_iter=1000).fit(p, y)    # 기본 L2(C=1): 보정 점수끼리 상관이 커서 계수 안정화
    f = lr.predict_proba(p)[:, 1]
    t_low, t_high = fit_thresholds(f, y)
    tau = 1.0
    if use_tau:
        spread = p.max(axis=1) - p.min(axis=1)
        # 동점이면 작은 τ(더 보수적): 작은 것부터 보고 '더 클 때만' 교체
        best = None
        for t in TAUS:
            s = tau_score(to_bands(f, t_low, t_high, spread, t), y)
            if best is None or s > best[0]:
                best = (s, t)
        tau = best[1]
    return {"calibration": calib, "weights": lr.coef_[0].tolist(), "bias": float(lr.intercept_[0]),
            "tau": tau, "t_low": t_low, "t_high": t_high}


def predict_stacking(params: dict, raw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """→ (융합 점수 f, 구간). C3에서 banding.py가 같은 계산을 해야 한다."""
    p = calibrate(raw, params["calibration"])
    f = sigmoid(p @ np.asarray(params["weights"]) + params["bias"])
    spread = p.max(axis=1) - p.min(axis=1)
    return f, to_bands(f, params["t_low"], params["t_high"], spread, params["tau"])


# ---------------------------------------------------------------- 평가
def metrics(bands: np.ndarray, y: np.ndarray) -> dict:
    n_real, n_ai = int(np.sum(y == 0)), int(np.sum(y == 1))
    rs = int(np.sum((bands == STRONG) & (y == 0)))
    rw = int(np.sum((bands == WEAK) & (y == 0)))
    as_ = int(np.sum((bands == STRONG) & (y == 1)))
    aw = int(np.sum((bands == WEAK) & (y == 1)))
    decided = rs + rw + as_ + aw
    correct = rw + as_
    precision = as_ / (as_ + rs) if as_ + rs else float("nan")
    recall = as_ / n_ai
    f1 = 2 * precision * recall / (precision + recall) if precision + recall and not math.isnan(precision) else float("nan")
    return {
        "FPR": rs / n_real,                     # 실제 → strong
        "real_weak": rw / n_real,               # 실제 → weak (맞음)
        "recall": recall,                       # AI → strong (맞음)
        "ai_weak": aw / n_ai,                   # AI → weak (틀림)
        "precision": precision,                 # strong 중 AI
        "f1": f1,
        "decided_acc": correct / decided if decided else float("nan"),   # strong/weak로 판정한 것 중 맞음
        "accuracy": correct / len(y),           # 전체 중 맞게 판정 (uncertain은 맞음으로 세지 않음)
        "uncertain": 1 - decided / len(y),
        "n_real_strong": rs, "n_ai_weak": aw,
    }


def rule_bands(df: pd.DataFrame, models: list[str]) -> np.ndarray:
    th = banding.load_thresholds()
    no_file = ROOT / "ml" / "reports" / "__no_ensemble__.yaml"   # 규칙 방식 강제
    out = []
    for _, r in df.iterrows():
        bands = {m: banding.band(m, float(r[m]), th) for m in models}
        out.append(banding.overall(bands, ensemble_path=no_file)[0])
    return np.array(out, dtype=object)


def run_cv(df: pd.DataFrame, models: list[str]):
    raw = df[models].to_numpy(dtype=float)
    y = (df["label"] == "ai").to_numpy(dtype=int)
    groups = df["source_id"].to_numpy()

    methods = ["규칙 (thresholds.yaml)", "스태킹", "스태킹 (τ 끔)", "단순 평균"] + [f"{m} 단일" for m in models]
    pred = {k: np.empty(len(df), dtype=object) for k in methods}
    f_oof = np.zeros(len(df))
    fold_of = np.zeros(len(df), dtype=int)
    fold_params = []

    pred["규칙 (thresholds.yaml)"][:] = rule_bands(df, models)
    for k, (tr, te) in enumerate(GroupKFold(n_splits=N_SPLITS).split(raw, y, groups)):
        fold_of[te] = k
        params = fit_stacking(raw[tr], y[tr])
        fold_params.append(params)
        f_oof[te], pred["스태킹"][te] = predict_stacking(params, raw[te])

        p0 = fit_stacking(raw[tr], y[tr], use_tau=False)
        pred["스태킹 (τ 끔)"][te] = predict_stacking(p0, raw[te])[1]

        avg = raw.mean(axis=1)
        lo, hi = fit_thresholds(avg[tr], y[tr])
        pred["단순 평균"][te] = to_bands(avg[te], lo, hi)
        for i, m in enumerate(models):
            lo, hi = fit_thresholds(raw[tr, i], y[tr])
            pred[f"{m} 단일"][te] = to_bands(raw[te, i], lo, hi)
    return y, pred, f_oof, fold_of, fold_params


# ---------------------------------------------------------------- 보고서
def pct(x):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.1f}%"


def build_report(df, models, y, pred, f_oof, fold_of, fold_params, final, verdict) -> str:
    L = []
    w = L.append
    w(f"# 앙상블 비교표 (C2, {date.today().isoformat()})\n")
    w(f"`ml/fit_ensemble.py`가 생성. 데이터: `ml/scores.csv` {len(df)}장 (실제 {int((y == 0).sum())}, AI {int((y == 1).sum())}), "
      f"모델 {', '.join(models)}. GroupKFold(source_id, {N_SPLITS}-fold), 아래 수치는 모두 **평가 부분(out-of-fold)** 결과를 합친 것.\n")
    w("용어: FPR = 실제 사진 → 강함. 재현율 = AI → 강함. 정밀도 = 강함 중 AI. 판정 정확도 = 강함·약함으로 판정한 것 중 맞음. "
      "전체 정확도 = 전체 중 맞게 판정(어려움은 맞음으로 세지 않음).\n")

    w("## 1. 방식별 비교\n")
    w("| 방식 | FPR | 실제→약함 | 재현율 (AI→강함) | AI→약함 | 정밀도 | F1 | 판정 정확도 | 전체 정확도 | 어려움 |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    M = {}
    for k, b in pred.items():
        m = metrics(b, y)
        M[k] = m
        w(f"| {k} | {pct(m['FPR'])} ({m['n_real_strong']}장) | {pct(m['real_weak'])} | {pct(m['recall'])} | "
          f"{pct(m['ai_weak'])} ({m['n_ai_weak']}장) | {pct(m['precision'])} | {pct(m['f1'])} | {pct(m['decided_acc'])} | "
          f"{pct(m['accuracy'])} | {pct(m['uncertain'])} |")
    w("")
    w(f"- 스태킹 융합 점수 f의 AUC (out-of-fold): {roc_auc_score(y, f_oof):.3f}. "
      + ", ".join(f"{m} 원점수 AUC {roc_auc_score(y, df[m]):.3f}" for m in models) + "\n")

    w("## 2. fold별 편차\n")
    keys = ["규칙 (thresholds.yaml)", "스태킹", "단순 평균"] + [f"{m} 단일" for m in models if m == "bfree"]
    w("| fold | 실제 / AI | " + " | ".join(f"{k} FPR · 판정정확도 · 어려움" for k in keys) + " |")
    w("|---|---|" + "---|" * len(keys))
    for k in range(N_SPLITS):
        idx = fold_of == k
        cells = []
        for key in keys:
            m = metrics(pred[key][idx], y[idx])
            cells.append(f"{pct(m['FPR'])} · {pct(m['decided_acc'])} · {pct(m['uncertain'])}")
        w(f"| {k + 1} | {int((y[idx] == 0).sum())} / {int((y[idx] == 1).sum())} | " + " | ".join(cells) + " |")
    w("")
    w("fold별 스태킹 파라미터 (학습 부분에서만 맞춤):\n")
    w("| fold | 가중치 (" + ", ".join(models) + ") | τ | t_low | t_high |")
    w("|---|---|---|---|---|")
    for k, p in enumerate(fold_params):
        w(f"| {k + 1} | {', '.join(f'{x:.2f}' for x in p['weights'])} | {p['tau']:.1f} | {p['t_low']:.3f} | {p['t_high']:.3f} |")
    w("")

    w("## 3. 버전별 (규칙 · 스태킹 · B-Free 단일)\n")
    w("| 버전 | 방식 | FPR | 재현율 | AI→약함 | 판정 정확도 | 어려움 |")
    w("|---|---|---|---|---|---|---|")
    for v in ["original", "jpeg70", "resize50", "screenshot"]:
        idx = (df["version"] == v).to_numpy()
        for key in ["규칙 (thresholds.yaml)", "스태킹"] + [f"{m} 단일" for m in models if m == "bfree"]:
            m = metrics(pred[key][idx], y[idx])
            w(f"| {v} | {key} | {pct(m['FPR'])} | {pct(m['recall'])} | {pct(m['ai_weak'])} | {pct(m['decided_acc'])} | {pct(m['uncertain'])} |")
    w("")

    w("## 4. 채택 기준\n")
    for line in verdict["lines"]:
        w(f"- {line}")
    w("")
    w("## 5. 전체 데이터로 다시 맞춘 최종 파라미터\n")
    w("`ml/reports/ensemble.yaml` (채택 시 `--install`로 `inference/ensemble.yaml`에 복사):\n")
    w("```yaml")
    w(yaml.safe_dump(final, sort_keys=False, allow_unicode=True).rstrip())
    w("```\n")

    n_real_src = df.loc[df["label"] == "real", "source_id"].nunique()
    w("## 6. 데이터가 적어서 생기는 문제\n")
    w(f"- 독립 원본은 실제 {n_real_src}장뿐이다. fold당 평가 실제 원본은 약 {n_real_src // N_SPLITS}장(변형 포함 약 {n_real_src * 4 // N_SPLITS}장)이라 "
      f"FPR 1장 차이가 fold 안에서 약 {100 / (n_real_src * 4 // N_SPLITS):.1f}%p다. 같은 원본의 변형끼리 점수가 비슷하므로 실제 변동은 이보다 크다.")
    w("- t_high(FPR 5%)와 t_low(AI→약함 5%)는 학습 부분 실제·AI 약 320장의 상위·하위 16장 근처에서 정해진다. 그 근처 몇 장에 따라 값이 크게 움직인다(§2 fold별 파라미터).")
    w(f"- τ는 후보 {len(TAUS)}개 중 학습 점수로 고른다. fold마다 다른 τ가 나오면 선택이 불안정하다는 뜻이다(§2).")
    w("- 규칙 방식의 thresholds.yaml은 800장 전체로 정했으므로 이 비교에서 규칙 쪽이 약간 유리하다.")
    w("- 실제 사진 출처는 RAISE 풍경 한 곳, AI는 Cloudflare Workers AI 생성기 3종뿐이다. 휴대폰 사진·다른 생성기에서는 결과가 다를 수 있다.")
    return "\n".join(L) + "\n"


def judge(M: dict, models: list[str], df: pd.DataFrame) -> dict:
    s, r = M["스태킹"], M["규칙 (thresholds.yaml)"]
    c1 = s["FPR"] <= r["FPR"]
    c2 = s["decided_acc"] >= r["decided_acc"]
    best = max(models, key=lambda m: roc_auc_score((df["label"] == "ai").astype(int), df[m]))
    b = M[f"{best} 단일"]
    c3 = s["FPR"] < b["FPR"]
    lines = [
        f"① 스태킹 FPR ≤ 규칙 FPR: {pct(s['FPR'])} vs {pct(r['FPR'])} → {'충족' if c1 else '미충족'}",
        f"② 스태킹 판정 정확도 ≥ 규칙: {pct(s['decided_acc'])} vs {pct(r['decided_acc'])} → {'충족' if c2 else '미충족'}",
        f"→ 계획서 §5.3 채택 기준: {'**충족**' if c1 and c2 else '**미충족** (단계 0 규칙으로 시연)'}",
        f"③ §12.4 (①② 충족 시에만 해당): 스태킹 FPR < 단일 최고 모델({best}, AUC 기준) FPR: "
        f"{pct(s['FPR'])} vs {pct(b['FPR'])} → {'충족' if c3 else f'미충족 (스태킹 대신 {best} 단일)'}",
        "최종 결정은 팀(C4)이 한다.",
    ]
    return {"adopt": c1 and c2, "lines": lines}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default=str(SCORES))
    ap.add_argument("--models", help="쉼표 구분 (없으면 DETECTORS 환경 변수 또는 기본값)")
    ap.add_argument("--install", action="store_true", help="채택 기준을 넘으면 inference/ensemble.yaml에 복사 (C3 이후)")
    args = ap.parse_args()

    models = args.models.split(",") if args.models else active_names()
    df = pd.read_csv(args.scores)
    missing = [m for m in models if m not in df.columns]
    if missing:
        sys.exit(f"scores.csv에 {missing} 열이 없습니다")
    df = df.dropna(subset=models).reset_index(drop=True)

    y, pred, f_oof, fold_of, fold_params = run_cv(df, models)
    M = {k: metrics(b, y) for k, b in pred.items()}
    verdict = judge(M, models, df)

    p = fit_stacking(df[models].to_numpy(dtype=float), y)
    r6 = lambda x: round(float(x), 6)  # noqa: E731
    final = {
        "calibration": {m: [r6(a), r6(b)] for m, (a, b) in zip(models, p["calibration"])},
        "stacking": {"weights": [r6(x) for x in p["weights"]], "bias": r6(p["bias"])},
        "disagreement_tau": r6(p["tau"]),
        "bands": {"low": r6(p["t_low"]), "high": r6(p["t_high"])},
        "trained_on": f"{len(df)}장 (실제 {int((y == 0).sum())}, AI {int((y == 1).sum())}, {date.today().isoformat()})",
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    out_yaml = REPORTS / "ensemble.yaml"
    with out_yaml.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# ensemble.yaml — ml/fit_ensemble.py가 생성. 손으로 고치지 않는다 (계획서 §5.3).\n")
        yaml.safe_dump(final, f, sort_keys=False, allow_unicode=True)
    report = build_report(df, models, y, pred, f_oof, fold_of, fold_params, final, verdict)
    (REPORTS / "ensemble_compare.md").write_text(report, encoding="utf-8", newline="\n")

    for line in verdict["lines"]:
        print(line)
    print(f"→ {REPORTS / 'ensemble_compare.md'}\n→ {out_yaml}")
    if args.install:
        if verdict["adopt"]:
            shutil.copyfile(out_yaml, INSTALL_PATH)
            print(f"→ {INSTALL_PATH} (서버가 스태킹을 쓴다. C3 구현 전이면 /analyze가 500)")
        else:
            print("채택 기준 미충족: inference/ensemble.yaml에 넣지 않았다.")


if __name__ == "__main__":
    main()
