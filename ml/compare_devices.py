"""CPU 점수와 GPU 점수를 비교한다 (inference/README.md 'GPU 실행').

경계값(thresholds.yaml)은 CPU 점수로 정했으므로, GPU로 옮길 때 구간·종합 판정이 바뀌는 이미지가
없는지 확인한다.

    # 1) GPU로 채점 (CPU 점수 ml/scores.csv는 이미 있음)
    DEVICE=cuda python ml/score_samples.py --out ml/scores_gpu.csv          # PowerShell: $env:DEVICE="cuda"
    # 2) 비교
    python ml/compare_devices.py --cpu ml/scores.csv --gpu ml/scores_gpu.csv

출력: 모델별 최대·평균 점수 차이, 구간이 바뀐 이미지 수, 종합 판정이 바뀐 이미지 수(와 그 image_id).
두 파일에 모두 있는 image_id·모델만 비교한다. 점수 파일은 소수점 6자리로 저장되므로 1e-6 미만 차이는 보이지 않는다.
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "inference"))

import banding  # noqa: E402


def read(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return {row["image_id"]: row for row in csv.DictReader(f)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cpu", type=Path, default=ROOT / "ml" / "scores.csv")
    p.add_argument("--gpu", type=Path, default=ROOT / "ml" / "scores_gpu.csv")
    args = p.parse_args()

    cpu, gpu = read(args.cpu), read(args.gpu)
    thresholds = banding.load_thresholds()
    ids = sorted(set(cpu) & set(gpu))
    models = [m for m in thresholds if ids and cpu[ids[0]].get(m) and gpu[ids[0]].get(m)]
    if not ids or not models:
        print("비교할 이미지·모델이 없습니다")
        return 1

    band_changed = {m: [] for m in models}
    diffs = {m: [] for m in models}
    overall_changed = []
    for i in ids:
        bc, bg = {}, {}
        for m in models:
            sc, sg = float(cpu[i][m]), float(gpu[i][m])
            diffs[m].append(abs(sc - sg))
            bc[m], bg[m] = banding.band(m, sc, thresholds), banding.band(m, sg, thresholds)
            if bc[m] != bg[m]:
                band_changed[m].append(i)
        if banding._rule(list(bc.values())) != banding._rule(list(bg.values())):
            overall_changed.append(i)

    print(f"비교한 이미지: {len(ids)}장, 모델: {', '.join(models)}")
    for m in models:
        d = diffs[m]
        print(f"  {m:8s} 최대 차이 {max(d):.6f}  평균 {sum(d) / len(d):.6f}  구간 바뀜 {len(band_changed[m])}장"
              + (f"  {band_changed[m][:10]}" if band_changed[m] else ""))
    print(f"종합 판정 바뀜: {len(overall_changed)}장" + (f"  {overall_changed[:20]}" if overall_changed else ""))
    return 0 if not overall_changed and not any(band_changed.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
