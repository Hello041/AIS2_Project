"""검증 데이터 전체를 detector로 채점해 ml/scores.csv에 저장한다 (계획서 B6).

    python ml/score_samples.py                      # manifest 전체, 모델은 DETECTORS 또는 기본(commfor, aide, bfree)
    python ml/score_samples.py --limit 5            # 시험: 아직 안 한 것 중 5장만
    python ml/score_samples.py --models commfor,aide # 일부 모델만 (새 파일로 시작할 때)
    python ml/score_samples.py --manifest ml/data/holdout/manifest.csv --out ml/scores_holdout.csv   # 확인용 데이터

- 서버(inference/main.py)와 같은 detector를 쓴다 → 점수가 서버 결과와 같다.
- 한 장 끝날 때마다 바로 저장한다. 끊겨도 다시 실행하면 이미 채점한 image_id는 건너뛴다.
- 세 모델 기준 한 장 약 17초(B-Free 12초) → 800장 약 4시간. 밤에 돌려 두는 것을 권장.
- scores.csv는 커밋하지 않는다(.gitignore).

열: image_id, source_id, label, version, generator, <모델>, ..., <모델>_ms, ...
  <모델>_ms가 비어 있는 행은 다른 채점에서 가져온 점수다(시간 기록 없음).
"""
import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "inference"))

from PIL import Image  # noqa: E402

from detectors import active_names, create_detectors  # noqa: E402

MANIFEST = ROOT / "ml" / "data" / "manifest.csv"
DATA_DIR = ROOT / "ml" / "data"
META = ["image_id", "source_id", "label", "version", "generator"]


def columns(models: list[str]) -> list[str]:
    return META + models + [f"{m}_ms" for m in models]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--models", help="쉼표 구분 (없으면 DETECTORS 환경 변수 또는 기본값)")
    p.add_argument("--out", default=str(ROOT / "ml" / "scores.csv"))
    p.add_argument("--limit", type=int, help="이번에 채점할 최대 장수 (시험용)")
    p.add_argument("--manifest", default=str(MANIFEST), help="대상 manifest (기본 ml/data/manifest.csv)")
    args = p.parse_args()

    models = args.models.split(",") if args.models else active_names()
    out = Path(args.out)
    header = columns(models)

    done = set()
    if out.exists():
        with out.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != header:
                sys.exit(f"{out}의 열이 이번 모델 구성과 다릅니다.\n  파일: {reader.fieldnames}\n  이번: {header}\n"
                         "모델 구성을 바꿨다면 다른 --out으로 새로 시작하세요.")
            done = {r["image_id"] for r in reader}

    with Path(args.manifest).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    todo = [r for r in rows if r["image_id"] not in done]
    if args.limit is not None:
        todo = todo[:args.limit]
    print(f"manifest {len(rows)}장 / 이미 채점 {len(done)}장 / 이번에 {len(todo)}장 · 모델 {models}", flush=True)
    if not todo:
        return

    t = time.perf_counter()
    detectors = create_detectors(models, load=True)
    print(f"모델 로드 {time.perf_counter() - t:.0f}초", flush=True)

    new_file = not out.exists()
    started = time.perf_counter()
    with out.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        if new_file:
            w.writeheader()
        for i, r in enumerate(todo, 1):
            with Image.open(DATA_DIR / r["file_path"]) as img:
                img.load()
                rec = {k: r[k] for k in META}
                for d in detectors:
                    t = time.perf_counter()
                    rec[d.name] = f"{d.score(img):.6f}"
                    rec[f"{d.name}_ms"] = round((time.perf_counter() - t) * 1000)
            w.writerow(rec)
            f.flush()  # 끊겨도 여기까지는 남는다
            if i % 10 == 0 or i == len(todo):
                per = (time.perf_counter() - started) / i
                left = per * (len(todo) - i)
                print(f"  {i}/{len(todo)}  장당 {per:.1f}초  남은 시간 약 {left / 60:.0f}분", flush=True)
    print(f"완료 → {out}")


if __name__ == "__main__":
    main()
