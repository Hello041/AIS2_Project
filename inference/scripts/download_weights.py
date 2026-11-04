"""모델 공식 코드와 가중치를 내려받는다.

    python inference/scripts/download_weights.py              # 전부
    python inference/scripts/download_weights.py --only npr   # 일부 (univfd,npr,aide)
    python inference/scripts/download_weights.py --list       # 받지 않고 URL·저장 경로만 출력

- 공식 코드: inference/third_party/{univfd,npr,aide}/ (커밋 고정, git 제외)
- 가중치:   inference/weights/{univfd,npr,aide}/  (git 제외)
- 이미 있는 파일은 건너뛴다. 끝나면 파일마다 크기와 sha256을 출력한다.
- AIDE 체크포인트는 Google Drive에 있어 gdown이 필요하다.
"""
import argparse
import hashlib
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

INFERENCE = Path(__file__).resolve().parents[1]
WEIGHTS = INFERENCE / "weights"
THIRD_PARTY = INFERENCE / "third_party"

# 공식 저장소. sha를 바꾸면 README의 표도 같이 고친다.
CODE = {
    "univfd": ("WisconsinAIVision/UniversalFakeDetect", "030495aea3300a8b54c0ec37ec7fe1dd7e63c619"),
    "npr": ("chuangchuangtan/NPR-DeepfakeDetection", "781ced3f7ca2cdc69ec9dd4ef27e8d0b3c07752a"),
    "aide": ("shilinyan99/AIDE", "6725b710d5c437ab2f59792908ce0377dfc907de"),
}

# (모델, 저장 경로[weights/ 기준], 출처). 출처는 URL 또는 ("gdrive_folder", 폴더 ID, 파일 이름).
FILES = [
    ("univfd", "univfd/fc_weights.pth",
     f"https://raw.githubusercontent.com/{CODE['univfd'][0]}/{CODE['univfd'][1]}/pretrained_weights/fc_weights.pth"),
    ("univfd", "univfd/ViT-L-14.pt",
     "https://openaipublic.azureedge.net/clip/models/"
     "b8cca3fd41ae0c99ba7e8951adf17d267cdb84cd88be6f7c2e0eca1737a03836/ViT-L-14.pt"),
    ("npr", "npr/model_epoch_last_3090.pth",
     f"https://raw.githubusercontent.com/{CODE['npr'][0]}/{CODE['npr'][1]}/model_epoch_last_3090.pth"),
    ("aide", "aide/sd14_train.pth",
     ("gdrive_folder", "1qx76UFvDpgCxaPLBCmsA2WY-SSzeJrd4", "sd14_train.pth")),
]

# 내용이 알려진 파일의 sha256 (OpenAI가 URL에 넣어 둔 값). 다르면 경고한다.
KNOWN_SHA256 = {
    "univfd/ViT-L-14.pt": "b8cca3fd41ae0c99ba7e8951adf17d267cdb84cd88be6f7c2e0eca1737a03836",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024


def fetch_url(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "ais2-download-weights"})
    with urllib.request.urlopen(req) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {human(done)} / {human(total)}", end="", flush=True)
    print()
    tmp.replace(dest)


def fetch_gdrive(folder_id: str, filename: str, dest: Path) -> None:
    try:
        import gdown
    except ImportError:
        sys.exit("gdown이 없습니다: pip install -r inference/requirements.txt")
    entries = gdown.download_folder(id=folder_id, skip_download=True, quiet=True)
    match = [e for e in entries or [] if Path(e.path).name == filename]
    if not match:
        sys.exit(f"Google Drive 폴더 {folder_id}에서 {filename}을 찾지 못했습니다")
    file_id = match[0].id
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        ok = gdown.download(id=file_id, output=str(tmp), quiet=False) is not None
    except Exception as e:  # Drive 다운로드 한도 초과 등
        print(f"  {type(e).__name__}: {str(e).splitlines()[0]}")
        ok = False
    if not ok:
        tmp.unlink(missing_ok=True)
        sys.exit(
            f"\n{filename} 다운로드 실패. 브라우저(구글 로그인 상태)에서 직접 받아 아래 경로에 두세요:\n"
            f"  https://drive.google.com/file/d/{file_id}/view\n"
            f"  -> {dest}"
        )
    tmp.replace(dest)


def fetch_code(name: str) -> None:
    repo, sha = CODE[name]
    dest = THIRD_PARTY / name
    if dest.exists():
        print(f"[건너뜀] 코드 {name}: {dest.relative_to(INFERENCE)} 있음")
        return
    url = f"https://codeload.github.com/{repo}/zip/{sha}"
    print(f"[코드] {name}: {repo}@{sha[:7]}")
    req = urllib.request.Request(url, headers={"User-Agent": "ais2-download-weights"})
    with urllib.request.urlopen(req) as r:
        data = r.read()
    tmp = THIRD_PARTY / f".{name}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        # 가중치 파일은 weights/로 따로 받으므로 코드 폴더에는 풀지 않는다.
        members = [m for m in z.namelist() if not m.endswith((".pth", ".pt", ".bin"))]
        z.extractall(tmp, members)
    (top,) = list(tmp.iterdir())
    top.replace(dest)
    tmp.rmdir()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="쉼표로 구분한 모델 이름 (univfd,npr,aide)")
    p.add_argument("--list", action="store_true", help="URL과 저장 경로만 출력")
    p.add_argument("--skip-code", action="store_true", help="공식 코드는 받지 않음")
    args = p.parse_args()

    names = args.only.split(",") if args.only else list(CODE)
    unknown = set(names) - set(CODE)
    if unknown:
        sys.exit(f"모르는 모델: {', '.join(sorted(unknown))}")

    if args.list:
        for name in names:
            repo, sha = CODE[name]
            print(f"코드  {name:7} https://github.com/{repo}/tree/{sha}  ->  third_party/{name}/")
        for name, rel, src in FILES:
            if name in names:
                where = src if isinstance(src, str) else f"https://drive.google.com/drive/folders/{src[1]} 의 {src[2]}"
                print(f"가중치 {name:7} {where}  ->  weights/{rel}")
        return

    THIRD_PARTY.mkdir(exist_ok=True)
    if not args.skip_code:
        for name in names:
            fetch_code(name)

    for name, rel, src in FILES:
        if name not in names:
            continue
        dest = WEIGHTS / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            print(f"[건너뜀] weights/{rel} 있음")
        else:
            print(f"[받는 중] weights/{rel}")
            if isinstance(src, str):
                fetch_url(src, dest)
            else:
                fetch_gdrive(src[1], src[2], dest)

    print("\n파일 | 크기 | sha256")
    for name, rel, _ in FILES:
        dest = WEIGHTS / rel
        if name in names and dest.exists():
            digest = sha256(dest)
            warn = ""
            if rel in KNOWN_SHA256 and KNOWN_SHA256[rel] != digest:
                warn = "  <-- 알려진 값과 다름!"
            print(f"weights/{rel} | {human(dest.stat().st_size)} | {digest}{warn}")


if __name__ == "__main__":
    main()
