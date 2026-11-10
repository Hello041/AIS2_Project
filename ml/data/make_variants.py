"""manifest의 version=original 행마다 변형 버전을 만들어 images/에 저장하고 manifest에 행을 추가한다 (B5).

    python ml/data/make_variants.py                         # 기본: jpeg70 (MVP)
    python ml/data/make_variants.py --versions all          # jpeg70, resize50, screenshot
    python ml/data/make_variants.py --versions resize50,screenshot --dry-run

변형 함수와 설정은 inference/variants.py 한 곳에만 있다(Sprint 2 서버 판정 안정성도 같은 함수를 쓴다).
이미 manifest에 있는 image_id는 건너뛴다. 끝나면 validate_manifest.py를 실행한다.
"""
import argparse
import csv
import subprocess
import sys
from pathlib import Path

from PIL import Image

DATA = Path(__file__).resolve().parent
ROOT = DATA.parents[1]
sys.path.insert(0, str(ROOT / "inference"))
import variants  # noqa: E402  (inference/variants.py)

MANIFEST = DATA / "manifest.csv"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--versions", default="jpeg70", help="쉼표 구분 또는 all (jpeg70,resize50,screenshot)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    versions = list(variants.VERSIONS) if args.versions == "all" else args.versions.split(",")
    bad = set(versions) - set(variants.VERSIONS)
    if bad:
        sys.exit(f"모르는 version: {', '.join(sorted(bad))}")

    with MANIFEST.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header, rows = reader.fieldnames, list(reader)
    have = {r["image_id"] for r in rows}
    originals = [r for r in rows if r["version"] == "original"]

    todo = []
    for r in originals:
        for v in versions:
            image_id = f"{r['source_id']}_{v}"
            if image_id not in have:
                todo.append((r, v, image_id))
    print(f"원본 {len(originals)}장 × {versions} → 이미 있음 {len(originals) * len(versions) - len(todo)}, 이번에 {len(todo)}건")
    if args.dry_run:
        for r, v, image_id in todo[:3]:
            print(f"  {r['file_path']} -> images/{r['label']}/{image_id}.{variants.EXTENSIONS[v]}")
        return

    new_rows = []
    for i, (r, v, image_id) in enumerate(todo, 1):
        rel = f"images/{r['label']}/{image_id}.{variants.EXTENSIONS[v]}"
        dest = DATA / rel
        if dest.exists():
            sys.exit(f"{rel}가 이미 있는데 manifest에는 없습니다. 지우고 다시 실행하세요.")
        with Image.open(DATA / r["file_path"]) as img:
            data, _ = variants.encode_variant(img, v)
        dest.write_bytes(data)
        # 변형 행은 원본 행의 label·generator·source_url·license·collected_by를 그대로 복사 (ml/data/README.md)
        new_rows.append({**r, "image_id": image_id, "version": v, "file_path": rel,
                         "notes": f"{r['image_id']}의 변형: {variants.DESCRIPTIONS[v]}"})
        if i % 100 == 0:
            print(f"  {i}/{len(todo)}")

    with MANIFEST.open("a", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=header, lineterminator="\n").writerows(new_rows)
    print(f"manifest.csv에 {len(new_rows)}행 추가\n")
    sys.exit(subprocess.call([sys.executable, str(DATA / "validate_manifest.py")]))


if __name__ == "__main__":
    main()
