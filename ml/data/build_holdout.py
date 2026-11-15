"""확인용(홀드아웃) 데이터의 원본을 정리해 holdout/images/에 넣고 holdout/manifest.csv를 만든다.

    python ml/data/build_holdout.py --dry-run
    python ml/data/build_holdout.py --collected-by 이름
    python ml/data/make_variants.py --manifest ml/data/holdout/manifest.csv --versions all   # 변형 3종

입력 (git 제외, holdout_kit/README.md로 수집):
    holdout/raise_holdout/png/raise_<id>.png, holdout/raise_holdout/sources.csv   RAISE 실제 사진 250장 (카테고리 포함)
    holdout/ais2_holdout_ai/<생성기>/ai_hold_NNN.{png,jpg}, log.jsonl             Cloudflare AI 250장

기존 800장과 **같은 변환**을 쓴다 (build_dataset.py의 convert_real·REAL_FORMATS·TARGET_AREA를 그대로 import).
  - 실제: 면적 1024x1024로 Lanczos 축소, 3장씩 돌아가며 PNG / JPEG q75 / JPEG q100 (4:2:0)
  - AI:   API 출력 그대로 복사
ID는 기존과 겹치지 않게 hreal_NNNN / hai_NNNN. manifest 형식은 기존과 같고(validate_manifest.py 통과),
카테고리(풍경·자연·건물·인물)는 holdout/categories.csv(source_id, category)에 따로 둔다.
실제 사진은 RAISE 원본 ID 순, AI는 ai_hold 번호 순으로 번호를 매긴다.
"""
import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

from build_dataset import AI_GENERATORS, HEADER, REAL_FORMATS, REAL_LICENSE, REAL_SOURCE_URL, convert_real

DATA = Path(__file__).resolve().parent
HOLD = DATA / "holdout"
RAISE_DIR = HOLD / "raise_holdout"
AI_DIR = HOLD / "ais2_holdout_ai"
MANIFEST = HOLD / "manifest.csv"
CATEGORIES = HOLD / "categories.csv"

# gen_cloudflare.py의 생성기 이름 → manifest의 generator 값 (기존 800장과 같은 이름)
GEN_NAME = {"sdxl": "sdxl", "sdxl_lightning": "sdxl-lightning", "flux_schnell": "flux1-schnell"}
MODEL = {name: (model_id, lic) for name, model_id, lic in AI_GENERATORS}


def plan_real(collected_by: str) -> list[dict]:
    with (RAISE_DIR / "sources.csv").open(encoding="utf-8-sig", newline="") as f:
        sources = sorted(csv.DictReader(f), key=lambda r: r["original_id"])
    jobs = []
    for i, s in enumerate(sources, start=1):
        src = RAISE_DIR / "png" / s["file"]
        if not src.exists():
            sys.exit(f"{src} 없음 (sources.csv에는 있음)")
        ext, quality = REAL_FORMATS[(i - 1) % len(REAL_FORMATS)]
        sid = f"hreal_{i:04d}"
        jobs.append({
            "kind": "real", "src": src, "quality": quality, "category": s["category"],
            "row": {
                "image_id": f"{sid}_original", "source_id": sid, "label": "real", "version": "original",
                "file_path": f"holdout/images/real/{sid}_original.{ext}", "generator": "camera",
                "source_url": REAL_SOURCE_URL, "license": REAL_LICENSE, "collected_by": collected_by,
            },
        })
    print(f"실제 사진: {len(jobs)}장")
    return jobs


def plan_ai(collected_by: str) -> list[dict]:
    log = {}
    with (AI_DIR / "log.jsonl").open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                log[r["image_id"]] = r   # 재실행으로 중복된 줄은 마지막 것
    jobs = []
    for i, (hold_id, r) in enumerate(sorted(log.items()), start=1):
        src = AI_DIR / r["file"]
        if not src.exists():
            sys.exit(f"{src} 없음 (log.jsonl에는 있음)")
        gen = GEN_NAME[r["generator"]]
        model_id, license_ = MODEL[gen]
        if r["model_id"] != model_id:
            sys.exit(f"{hold_id}: 모델 {r['model_id']} != {model_id}")
        sid = f"hai_{i:04d}"
        seed = r["seed"] if r.get("seed") is not None else "없음"
        jobs.append({
            "kind": "ai", "src": src, "category": r["category"],
            "row": {
                "image_id": f"{sid}_original", "source_id": sid, "label": "ai", "version": "original",
                "file_path": f"holdout/images/ai/{sid}_original{src.suffix.lower()}", "generator": gen,
                "source_url": "", "license": license_, "collected_by": collected_by,
                "notes": f"Cloudflare Workers AI {model_id}; 원본 {src.name}; API 출력 그대로; seed {seed}; "
                         f"prompt: {r['prompt']}",
            },
        })
    print(f"AI 이미지: {len(jobs)}장")
    return jobs


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--collected-by", default="")
    args = p.parse_args()

    if MANIFEST.exists():
        sys.exit(f"{MANIFEST.relative_to(DATA)}가 이미 있습니다. 다시 만들려면 holdout/manifest.csv, categories.csv, "
                 "images/를 지우고 실행하세요.")
    jobs = plan_real(args.collected_by) + plan_ai(args.collected_by)
    if args.dry_run:
        for j in jobs[:3] + jobs[-3:]:
            print(f"  {j['src'].relative_to(DATA)} -> {j['row']['file_path']} ({j['category']})")
        cats = {}
        for j in jobs:
            cats.setdefault(j["row"]["label"], {}).setdefault(j["category"], 0)
            cats[j["row"]["label"]][j["category"]] += 1
        print("카테고리:", cats)
        return

    rows = []
    for k, j in enumerate(jobs, 1):
        dest = DATA / j["row"]["file_path"]
        if dest.exists():
            sys.exit(f"{dest.relative_to(DATA)}가 이미 있습니다. holdout/images/를 지우고 다시 실행하세요.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if j["kind"] == "real":
            j["row"]["notes"] = convert_real(j, dest)
        else:
            shutil.copyfile(j["src"], dest)
        rows.append({h: j["row"].get(h, "") for h in HEADER})
        if k % 100 == 0:
            print(f"  {k}/{len(jobs)}")

    with MANIFEST.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with CATEGORIES.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["source_id", "category"])
        w.writerows((j["row"]["source_id"], j["category"]) for j in jobs)
    print(f"{MANIFEST.relative_to(DATA)} {len(rows)}행, {CATEGORIES.relative_to(DATA)}\n")
    sys.exit(subprocess.call([sys.executable, str(DATA / "validate_manifest.py"), str(MANIFEST)]))


if __name__ == "__main__":
    main()
