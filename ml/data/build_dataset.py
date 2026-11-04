"""incoming/의 원본을 정리해 images/에 'original' 버전으로 넣고 manifest.csv에 행을 추가한다.

    python ml/data/build_dataset.py --dry-run          # 무엇을 할지 출력만
    python ml/data/build_dataset.py --collected-by 이름

입력 (git 제외):
    incoming/real/*.png   RAISE 실제 사진 (풍경·자연, 약 1,600만 화소 PNG)
    incoming/ai/ai_land_NNN.{png,jpg}   Cloudflare Workers AI 생성 (약 100만 화소)

실제 사진과 AI 이미지가 해상도·형식만으로 구분되지 않도록 실제 사진을 AI 쪽 조건에 맞춘다
(2026-11-04 결정, ml/data/README.md '데이터 구성' 참고).
  - 실제: 면적이 1024x1024(약 105만 화소)가 되도록 Lanczos 축소, 3장씩 돌아가며
          PNG / JPEG 품질 75 / JPEG 품질 100 (4:2:0) — AI 생성기 3종의 출력 형식과 같은 비율
  - AI:   받은 파일을 그대로 복사 (API 출력 그대로)

이미 manifest에 있는 image_id는 건너뛴다. 끝나면 validate_manifest.py를 실행한다.
"""
import argparse
import csv
import hashlib
import math
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

DATA = Path(__file__).resolve().parent
INCOMING = DATA / "incoming"
MANIFEST = DATA / "manifest.csv"
HEADER = ["image_id", "source_id", "label", "version", "file_path",
          "generator", "source_url", "license", "collected_by", "notes"]

REAL_COUNT = 100           # 계획서 §12.4: 실제 100 + AI 100 (원본 기준)
REAL_SEED = 42             # 실제 사진 선택 시드 (바꾸면 다른 100장이 뽑힌다)
TARGET_AREA = 1024 * 1024  # AI 이미지 해상도(1024x1024, 1152x896)와 맞춤
REAL_SOURCE_URL = "http://loki.disi.unitn.it/RAISE/"
REAL_LICENSE = "RAISE-research-only"

# 실제 사진 저장 형식: AI 생성기 3종(sdxl=PNG, sdxl-lightning=JPEG q75, flux1-schnell=JPEG q100)과 같은 비율
REAL_FORMATS = [("png", None), ("jpg", 75), ("jpg", 100)]

# 생성 스크립트(gen_cloudflare.py)의 순환 규칙: 번호 k(0부터) % 3
AI_GENERATORS = [
    ("sdxl", "@cf/stabilityai/stable-diffusion-xl-base-1.0", "CreativeML-OpenRAIL++-M"),
    ("sdxl-lightning", "@cf/bytedance/stable-diffusion-xl-lightning", "CreativeML-OpenRAIL++-M"),
    ("flux1-schnell", "@cf/black-forest-labs/flux-1-schnell", "Apache-2.0"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def existing_ids() -> set[str]:
    with MANIFEST.open(encoding="utf-8-sig", newline="") as f:
        return {row["image_id"] for row in csv.DictReader(f)}


def plan_real(collected_by: str) -> list[dict]:
    files = sorted((INCOMING / "real").glob("*.png"))
    seen, unique, dups = {}, [], []
    for p in files:
        h = sha256(p)
        if h in seen:
            dups.append((p.name, seen[h]))
        else:
            seen[h] = p.name
            unique.append(p)
    for a, b in dups:
        print(f"[중복 제외] real/{a} = real/{b}")
    if len(unique) < REAL_COUNT:
        sys.exit(f"실제 사진이 {len(unique)}장뿐입니다 (필요 {REAL_COUNT})")
    chosen = sorted(random.Random(REAL_SEED).sample(unique, REAL_COUNT))
    print(f"실제 사진: {len(files)}장 중 중복 {len(dups)}장 제외, {len(unique)}장에서 {REAL_COUNT}장 선택 (시드 {REAL_SEED})")

    jobs = []
    for i, src in enumerate(chosen, start=1):
        ext, quality = REAL_FORMATS[(i - 1) % len(REAL_FORMATS)]
        sid = f"real_{i:04d}"
        jobs.append({
            "kind": "real", "src": src, "quality": quality,
            "row": {
                "image_id": f"{sid}_original", "source_id": sid, "label": "real", "version": "original",
                "file_path": f"images/real/{sid}_original.{ext}", "generator": "camera",
                "source_url": REAL_SOURCE_URL, "license": REAL_LICENSE, "collected_by": collected_by,
            },
        })
    return jobs


def plan_ai(collected_by: str) -> list[dict]:
    jobs = []
    for src in sorted((INCOMING / "ai").glob("ai_land_*.*")):
        m = re.fullmatch(r"ai_land_(\d+)", src.stem)
        if not m or src.suffix.lower() not in (".png", ".jpg"):
            print(f"[건너뜀] 이름 규칙 밖: ai/{src.name}")
            continue
        n = int(m.group(1))
        gen, model_id, license_ = AI_GENERATORS[(n - 1) % len(AI_GENERATORS)]
        sid = f"ai_{n:04d}"
        jobs.append({
            "kind": "ai", "src": src,
            "row": {
                "image_id": f"{sid}_original", "source_id": sid, "label": "ai", "version": "original",
                "file_path": f"images/ai/{sid}_original{src.suffix.lower()}", "generator": gen,
                "source_url": "", "license": license_, "collected_by": collected_by,
                "notes": f"Cloudflare Workers AI {model_id}; 원본 {src.name}; API 출력 그대로",
            },
        })
    print(f"AI 이미지: {len(jobs)}장")
    return jobs


def convert_real(job: dict, dest: Path) -> str:
    with Image.open(job["src"]) as im:
        im = im.convert("RGB")
        w, h = im.size
        s = math.sqrt(TARGET_AREA / (w * h))
        size = (round(w * s), round(h * s))
        out = im.resize(size, Image.LANCZOS)
    if job["quality"] is None:
        out.save(dest, "PNG")
        fmt = "PNG"
    else:
        out.save(dest, "JPEG", quality=job["quality"], subsampling=2)  # 2 = 4:2:0 (AI JPEG와 같음)
        fmt = f"JPEG q{job['quality']} 4:2:0"
    return f"RAISE {job['src'].stem}; {w}x{h}->{size[0]}x{size[1]} Lanczos; {fmt}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--collected-by", default="", help="manifest의 collected_by 값")
    args = p.parse_args()

    have = existing_ids()
    jobs = plan_real(args.collected_by) + plan_ai(args.collected_by)
    todo = [j for j in jobs if j["row"]["image_id"] not in have]
    print(f"manifest에 이미 있음 {len(jobs) - len(todo)}건, 이번에 추가 {len(todo)}건")
    if args.dry_run:
        for j in todo[:3] + todo[-3:]:
            print(" ", j["src"].name, "->", j["row"]["file_path"])
        return

    rows = []
    for j in todo:
        dest = DATA / j["row"]["file_path"]
        if dest.exists():
            sys.exit(f"{dest.relative_to(DATA)}가 이미 있는데 manifest에는 없습니다. 지우고 다시 실행하세요.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if j["kind"] == "real":
            j["row"]["notes"] = convert_real(j, dest)
        else:
            shutil.copyfile(j["src"], dest)
        rows.append({k: j["row"].get(k, "") for k in HEADER})

    with MANIFEST.open("a", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=HEADER, lineterminator="\n").writerows(rows)
    print(f"manifest.csv에 {len(rows)}행 추가\n")
    sys.exit(subprocess.call([sys.executable, str(DATA / "validate_manifest.py")]))


if __name__ == "__main__":
    main()
