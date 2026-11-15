"""확인용(홀드아웃) 데이터 평가 — 고정된 설정으로 딱 한 번 (holdout_kit/README.md '평가 규칙').

    python ml/eval_holdout.py --scores ml/scores_holdout.csv --categories ml/data/holdout/categories.csv
    python ml/eval_holdout.py --scores ml/scores.csv --out ml/reports/_eval_test.md   # 코드 시험용 (기존 800장)

- 판정: 서버와 같은 코드 — thresholds.yaml + banding 단계 0 규칙. ensemble.yaml(스태킹)은 쓰지 않는다
  (계획서 §7 '확인용 평가 전 설정 고정'에 적힌 방식). 이 스크립트는 설정을 바꾸는 기능이 없다.
- 보고: FPR, 실제→약함, AI→강함, AI→약함, 판정 정확도, '어려움' 비율
  + 95% 신뢰구간 (원본 ID 단위 부트스트랩: 같은 원본의 변형 4개를 한 묶음으로 뽑는다, 실제·AI 따로)
  + 변형별 · 카테고리별 · 생성기별 · 모델별(단일 막대) 결과
- 보고서 머리에 thresholds.yaml의 sha256을 적어, 평가에 쓴 설정이 고정본과 같은지 확인할 수 있게 한다.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "inference"))
sys.path.insert(0, str(ROOT / "ml"))

import banding  # noqa: E402
from detectors import active_names  # noqa: E402
from fit_ensemble import metrics, rule_bands  # noqa: E402  (판정 정확도 등 정의를 C2 비교표와 같게)

N_BOOT = 2000
SEED = 2026
TARGET_FPR = 0.05
KEYS = [("FPR", "FPR (실제→강함)"), ("real_weak", "실제→약함"), ("recall", "AI→강함"), ("ai_weak", "AI→약함"),
        ("decided_acc", "판정 정확도"), ("uncertain", "어려움")]


def pct(x) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.1f}%"


def bootstrap_ci(df: pd.DataFrame, bands: np.ndarray, y: np.ndarray) -> dict[str, tuple[float, float]]:
    """원본(source_id) 단위로, 실제·AI 원본을 각각 복원추출해 지표 분포의 2.5~97.5 백분위."""
    rng = np.random.default_rng(SEED)
    groups = {lab: [np.flatnonzero((df["source_id"] == s).to_numpy()) for s in df.loc[df["label"] == lab, "source_id"].unique()]
              for lab in ("real", "ai")}
    vals = {k: [] for k, _ in KEYS}
    for _ in range(N_BOOT):
        idx = np.concatenate([g[i] for lab in ("real", "ai") for g in [groups[lab]]
                              for i in rng.integers(0, len(groups[lab]), len(groups[lab]))])
        m = metrics(bands[idx], y[idx])
        for k, _ in KEYS:
            vals[k].append(m[k])
    return {k: (float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))) for k, v in vals.items()}


def table(df: pd.DataFrame, bands: np.ndarray, y: np.ndarray, col: str, order: list | None = None) -> list[str]:
    out = [f"| {col} | 실제 / AI (장) | " + " | ".join(name for _, name in KEYS) + " |",
           "|---|---|" + "---|" * len(KEYS)]
    values = order or sorted(df[col].dropna().unique())
    for v in values:
        idx = (df[col] == v).to_numpy()
        if not idx.any():
            continue
        yy = y[idx]
        if (yy == 0).sum() == 0 or (yy == 1).sum() == 0:
            # 한쪽 라벨만 있는 그룹(예: 생성기)은 그 라벨 지표만
            m = metrics(np.concatenate([bands[idx], [banding.UNCERTAIN]]), np.concatenate([yy, [1 - yy[0]]]))
            cells = [pct(m[k]) if (k in ("recall", "ai_weak") and yy[0] == 1) or (k in ("FPR", "real_weak") and yy[0] == 0)
                     else "—" for k, _ in KEYS]
        else:
            m = metrics(bands[idx], yy)
            cells = [pct(m[k]) for k, _ in KEYS]
        out.append(f"| {v} | {int((yy == 0).sum())} / {int((yy == 1).sum())} | " + " | ".join(cells) + " |")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", required=True, help="score_samples.py 결과 CSV")
    ap.add_argument("--categories", help="source_id,category CSV (확인용 데이터)")
    ap.add_argument("--out", default=str(ROOT / "ml" / "reports" / "holdout_eval.md"))
    args = ap.parse_args()

    models = active_names()
    df = pd.read_csv(args.scores)
    missing = [m for m in models if m not in df.columns]
    if missing:
        sys.exit(f"{args.scores}에 {missing} 열이 없습니다")
    if df[models].isna().any().any():
        sys.exit(f"점수가 빠진 행이 있습니다 ({int(df[models].isna().any(axis=1).sum())}행). 채점을 끝까지 하세요.")
    if args.categories:
        df = df.merge(pd.read_csv(args.categories), on="source_id", how="left", validate="many_to_one")
    y = (df["label"] == "ai").to_numpy(dtype=int)
    bands = rule_bands(df, models)
    m = metrics(bands, y)
    ci = bootstrap_ci(df, bands, y)
    th = banding.load_thresholds()
    th_sha = hashlib.sha256(banding.THRESHOLDS_PATH.read_bytes()).hexdigest()

    L = []
    w = L.append
    w(f"# 확인용(홀드아웃) 평가 ({date.today().isoformat()})\n")
    w(f"`ml/eval_holdout.py`가 생성. 점수: `{Path(args.scores).name}` {len(df)}장 "
      f"(실제 {int((y == 0).sum())}장 · 원본 {df.loc[df.label == 'real', 'source_id'].nunique()}개, "
      f"AI {int((y == 1).sum())}장 · 원본 {df.loc[df.label == 'ai', 'source_id'].nunique()}개).\n")
    w("## 평가에 쓴 설정 (고정본과 같은지 확인)\n")
    w(f"- 모델: {', '.join(models)}")
    w(f"- 경계값: " + ", ".join(f"{k} {lo}/{hi}" for k, (lo, hi) in th.items()))
    w(f"- `thresholds.yaml` sha256: `{th_sha}`")
    w(f"- 판정: 단계 0 규칙 (`banding.overall`, 스태킹 미사용)\n")

    w("## 1. 전체 결과\n")
    w("| 지표 | 값 | 95% 신뢰구간 |")
    w("|---|---|---|")
    for k, name in KEYS:
        w(f"| {name} | {pct(m[k])} | {pct(ci[k][0])} ~ {pct(ci[k][1])} |")
    w("")
    w(f"- 실제 사진 중 '강함' {m['n_real_strong']}장, AI 중 '약함' {m['n_ai_weak']}장.")
    w(f"- 목표 FPR ≤ {TARGET_FPR * 100:.0f}% (계획서 §12.4): 추정값 {pct(m['FPR'])} → "
      f"{'충족' if m['FPR'] <= TARGET_FPR else '미충족'}, 신뢰구간 상한 {pct(ci['FPR'][1])} → "
      f"{'상한도 목표 이내' if ci['FPR'][1] <= TARGET_FPR else '상한은 목표 초과 (데이터로 확신할 수 없음)'}.")
    w(f"- 신뢰구간: 원본 ID 단위 부트스트랩 {N_BOOT}회 (시드 {SEED}), 백분위 2.5~97.5.\n")

    w("## 2. 변형별\n")
    L += table(df, bands, y, "version", ["original", "jpeg70", "resize50", "screenshot"])
    w("")
    if "category" in df.columns:
        w("## 3. 카테고리별\n")
        L += table(df, bands, y, "category", ["landscape", "nature", "buildings", "people"])
        w("")
    w("## 4. 생성기별 (AI만)\n")
    L += table(df[df.label == "ai"], bands[df.label.to_numpy() == "ai"], y[y == 1], "generator")
    w("")
    w("## 5. 모델별 막대 (각 모델 단독 구간, thresholds.yaml)\n")
    w("| 모델 | FPR | 실제→약함 | AI→강함 | AI→약함 | 어려움 |")
    w("|---|---|---|---|---|---|")
    for name in models:
        b = np.array([banding.band(name, float(s), th) for s in df[name]], dtype=object)
        mm = metrics(b, y)
        w(f"| {name} | {pct(mm['FPR'])} | {pct(mm['real_weak'])} | {pct(mm['recall'])} | {pct(mm['ai_weak'])} | {pct(mm['uncertain'])} |")
    w("")
    w("## 6. 한계\n")
    w("- 이 데이터로는 한 번만 평가한다. 결과를 보고 설정을 바꾸면 이 데이터는 더 이상 확인용이 아니다.")
    w("- 실제 사진은 RAISE(야외, Nikon DSLR)뿐이다. 실내·휴대폰 사진은 들어 있지 않다.")
    w("- AI 생성기는 기존과 같은 3종이다. 처음 보는 생성기에 대한 성능은 알 수 없다.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print(f"FPR {pct(m['FPR'])} [{pct(ci['FPR'][0])}~{pct(ci['FPR'][1])}]  AI→강함 {pct(m['recall'])}  "
          f"AI→약함 {pct(m['ai_weak'])}  판정 정확도 {pct(m['decided_acc'])}  어려움 {pct(m['uncertain'])}")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
