"""manifest.csv 검사. 형식은 ml/data/README.md 참고.

종료 코드: 0 = 문제 없음, 1 = 문제 행 있음, 2 = 파일을 읽을 수 없거나 헤더 불일치.
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
HEADER = [
    "image_id", "source_id", "label", "version", "file_path",
    "generator", "source_url", "license", "collected_by", "notes",
]
REQUIRED = ["image_id", "source_id", "label", "version", "file_path"]
LABELS = {"real", "ai"}
VERSIONS = {"original", "jpeg70", "resize50", "screenshot"}


def validate(manifest: Path) -> int:
    try:
        f = manifest.open(encoding="utf-8", newline="")
    except OSError as e:
        print(f"읽을 수 없음: {manifest} ({e})")
        return 2

    with f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header != HEADER:
            print(f"헤더 불일치\n  기대: {','.join(HEADER)}\n  실제: {','.join(header or [])}")
            return 2

        problems: list[tuple[int, str]] = []
        seen_ids: dict[str, int] = {}
        labels_by_source: dict[str, set[str]] = defaultdict(set)
        rows_by_source: dict[str, list[int]] = defaultdict(list)

        for line_no, values in enumerate(reader, start=2):
            if not any(v.strip() for v in values):
                continue
            if len(values) != len(HEADER):
                problems.append((line_no, f"열 개수 {len(values)} (기대 {len(HEADER)})"))
                continue
            row = dict(zip(HEADER, values))

            for col in REQUIRED:
                if not row[col].strip():
                    problems.append((line_no, f"{col} 비어 있음"))

            if row["label"] and row["label"] not in LABELS:
                problems.append((line_no, f"label 허용값 아님: {row['label']!r}"))
            if row["version"] and row["version"] not in VERSIONS:
                problems.append((line_no, f"version 허용값 아님: {row['version']!r}"))

            image_id, source_id = row["image_id"], row["source_id"]
            if image_id and source_id and row["version"]:
                expected = f"{source_id}_{row['version']}"
                if image_id != expected:
                    problems.append((line_no, f"image_id {image_id!r} != {expected!r}"))
            if image_id:
                if image_id in seen_ids:
                    problems.append((line_no, f"image_id 중복: {image_id!r} (첫 등장 {seen_ids[image_id]}행)"))
                else:
                    seen_ids[image_id] = line_no

            if source_id and row["label"]:
                labels_by_source[source_id].add(row["label"])
                rows_by_source[source_id].append(line_no)

            if row["file_path"] and not (DATA_DIR / row["file_path"]).is_file():
                problems.append((line_no, f"파일 없음: {row['file_path']}"))

        for source_id, labels in labels_by_source.items():
            if len(labels) > 1:
                rows = ", ".join(map(str, rows_by_source[source_id]))
                problems.append((rows_by_source[source_id][0],
                                 f"source_id {source_id!r}에 label 혼재 {sorted(labels)} (행 {rows})"))

    for line_no, msg in sorted(problems):
        print(f"{line_no}행: {msg}")
    n_rows = len(seen_ids)
    if problems:
        print(f"문제 {len(problems)}건 (이미지 행 {n_rows}개)")
        return 1
    print(f"OK (이미지 행 {n_rows}개)")
    return 0


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR / "manifest.csv"
    sys.exit(validate(path))
