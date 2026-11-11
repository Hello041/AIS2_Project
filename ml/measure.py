"""모델별 메모리·추론 시간 측정 (계획서 §7).

    python ml/measure.py                          # 임의의 1024x1024 이미지
    python ml/measure.py ml/data/samples/x.png    # 지정 이미지
    python ml/measure.py --models univfd,bfree    # 일부 모델만 (npr은 비교 재현용)

- 모델마다 별도 프로세스에서 측정한다(서로의 메모리가 섞이지 않게). 마지막에 세 모델을 한 프로세스에 함께 올려 총 RSS와 순차 추론 시간을 잰다.
- 추론 시간은 PIL 이미지 → 원점수까지(전처리 포함). 워밍업 1회 후 5회 평균·최대. torch.inference_mode, 배치 1, CPU.
- detectors/가 생기기 전 임시 스크립트라 공식 코드(inference/third_party/)의 모델·전처리를 직접 쓴다.
"""
import argparse
import gc
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import psutil
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "inference" / "weights"
THIRD_PARTY = ROOT / "inference" / "third_party"
ALL_MODELS = ["univfd", "aide", "bfree"]  # npr은 --models npr로만 (2026-11-10 B-Free로 교체)
RUNS = 5

IMAGENET_MEAN, IMAGENET_STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
CLIP_MEAN = [0.48145466, 0.4578275, 0.40821073]
CLIP_STD = [0.26862954, 0.26130258, 0.27577711]


def _import_from(repo: str, module: str):
    """third_party/<repo>를 sys.path 맨 앞에 넣고 import. 저장소마다 'models' 같은 같은 이름 패키지가 있어서 정리한다."""
    for k in [k for k in sys.modules if k.split(".")[0] in ("models", "networks", "data")]:
        del sys.modules[k]
    sys.path.insert(0, str(THIRD_PARTY / repo))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


# ---------------------------------------------------------------- UnivFD
def load_univfd():
    """CLIP ViT-L/14 이미지 인코더만 만들고 visual.* 가중치만 올린다 (텍스트 인코더는 만들지 않음)."""
    from torchvision import transforms
    clip_model = _import_from("univfd", "models.clip.model")

    jit = torch.jit.load(str(WEIGHTS / "univfd" / "ViT-L-14.pt"), map_location="cpu")
    full = jit.state_dict()
    del jit
    sd = {k[len("visual."):]: v for k, v in full.items() if k.startswith("visual.")}
    del full
    gc.collect()

    width = sd["conv1.weight"].shape[0]
    patch = sd["conv1.weight"].shape[-1]
    layers = len({k.split(".")[2] for k in sd if k.startswith("transformer.resblocks.")})
    grid = round((sd["positional_embedding"].shape[0] - 1) ** 0.5)
    visual = clip_model.VisionTransformer(
        input_resolution=patch * grid, patch_size=patch, width=width,
        layers=layers, heads=width // 64, output_dim=sd["proj"].shape[1],
    )
    visual.load_state_dict(sd)
    visual = visual.float().eval()

    fc = torch.nn.Linear(sd["proj"].shape[1], 1)
    fc.load_state_dict(torch.load(WEIGHTS / "univfd" / "fc_weights.pth", map_location="cpu"))
    fc.eval()

    # 공식 validate.py: CenterCrop(224) → ToTensor → CLIP 정규화 (Resize 없음)
    tf = transforms.Compose([
        transforms.CenterCrop(224), transforms.ToTensor(), transforms.Normalize(CLIP_MEAN, CLIP_STD),
    ])

    def score(img: Image.Image) -> float:
        x = tf(img).unsqueeze(0)
        return torch.sigmoid(fc(visual(x))).item()

    return [visual, fc], score


# ---------------------------------------------------------------- NPR
def load_npr():
    from torchvision import transforms
    resnet = _import_from("npr", "networks.resnet")
    model = resnet.resnet50(num_classes=1)
    model.load_state_dict(torch.load(WEIGHTS / "npr" / "model_epoch_last_3090.pth", map_location="cpu"))
    model.eval()
    # AIGCDetectBenchmark 설정: no_resize, no_crop → ToTensor + ImageNet 정규화
    tf = transforms.Compose([transforms.ToTensor(), transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])

    def score(img: Image.Image) -> float:
        # NPR은 1/2 축소→확대 결과를 원본에서 빼므로 가로·세로가 홀수면 크기가 1px 어긋나 실패한다.
        # 짝수가 되도록 오른쪽·아래 1px을 잘라낸다.
        w, h = img.size
        if w % 2 or h % 2:
            img = img.crop((0, 0, w - w % 2, h - h % 2))
        return torch.sigmoid(model(tf(img).unsqueeze(0))).item()

    return [model], score


# ---------------------------------------------------------------- AIDE
def load_aide():
    from torchvision import transforms
    ckpt_path = WEIGHTS / "aide" / "sd14_train.pth"
    if not ckpt_path.exists():
        raise FileNotFoundError(f"{ckpt_path.relative_to(ROOT)} 없음")
    aide = _import_from("aide", "models.AIDE")
    # data/__init__.py가 kornia 등을 끌어오므로 dct.py만 파일로 직접 읽는다
    spec = importlib.util.spec_from_file_location("aide_dct", THIRD_PARTY / "aide" / "data" / "dct.py")
    dct_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dct_mod)

    # resnet_path·convnext_path=None: 백본은 무작위 초기화로 만들고 체크포인트로 전부 덮어쓴다
    model = aide.AIDE(resnet_path=None, convnext_path=None)
    ckpt = torch.load(ckpt_path, map_location="cpu")
    state = ckpt.get("model", ckpt)
    model.load_state_dict(state, strict=True)  # 키가 하나라도 다르면 실패 (2026-11-04 전부 일치 확인)
    del ckpt, state
    gc.collect()
    model.eval()
    dct = dct_mod.DCT_base_Rec_Module()

    # 공식 TestDataset: ToTensor → DCT 4개 뷰 + 원본 → 각각 Resize(256,256) + ImageNet 정규화
    to_tensor = transforms.ToTensor()
    post = transforms.Compose([transforms.Resize([256, 256], antialias=None),
                               transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])

    def score(img: Image.Image) -> float:
        x = to_tensor(img)
        views = [post(v) for v in dct(x)] + [post(x)]
        logits = model(torch.stack(views).unsqueeze(0))
        return torch.softmax(logits, dim=1)[0, 1].item()  # 1 = fake

    return [model], score


# ---------------------------------------------------------------- B-Free
def load_bfree():
    """B-Free (CVPR 2025, GRIP-UNINA). ViT-B/14 DINOv2 + 레지스터 4개, 504x504 5-crop(가운데+네 모서리) 평균.

    공식 main_bfree_single.py와 같은 전처리: ToTensor + ImageNet 정규화, Resize·Crop 없음
    (504보다 작은 이미지는 모델 내부에서 반복해 채운다). 출력은 로짓 1개, 양수 = AI.
    """
    import yaml
    from torchvision import transforms
    wdir = WEIGHTS / "bfree" / "BFREE_dino2reg4"
    cfg = yaml.safe_load((wdir / "config.yaml").read_text())
    networks = _import_from("bfree/code", "networks")
    model = networks.get_network(cfg["arch"])  # pretrained=False: 인터넷에서 받지 않음
    model = networks.load_weights(model, str(wdir / cfg["weights_file"])).eval()
    assert cfg["norm_type"] == "resnet"
    tf = transforms.Compose([transforms.ToTensor(), transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])

    def score(img: Image.Image) -> float:
        logit = model(tf(img).unsqueeze(0))[:, 0]
        return torch.sigmoid(logit).item()

    score.logit = lambda img: model(tf(img).unsqueeze(0))[:, 0].item()  # 공식 결과와 비교용
    return [model], score


LOADERS = {"univfd": load_univfd, "npr": load_npr, "aide": load_aide, "bfree": load_bfree}


# ---------------------------------------------------------------- 측정
def rss() -> int:
    return psutil.Process().memory_info().rss


def peak_rss() -> int | None:
    mi = psutil.Process().memory_info()
    return getattr(mi, "peak_wset", None)  # Windows만. 다른 OS는 None


def time_runs(score, img):
    score(img)  # 워밍업
    times, value = [], None
    for _ in range(RUNS):
        t = time.perf_counter()
        value = score(img)
        times.append(time.perf_counter() - t)
    return value, times


def worker(names: list[str], image_path: str | None) -> dict:
    img = open_image(image_path)
    torch.set_grad_enabled(False)
    out = {"models": {}}
    base = rss()
    scorers = {}
    with torch.inference_mode():
        for name in names:
            before = rss()
            t = time.perf_counter()
            try:
                _, scorer = LOADERS[name]()
            except FileNotFoundError as e:
                out["models"][name] = {"error": str(e)}
                continue
            gc.collect()
            out["models"][name] = {"load_s": time.perf_counter() - t, "rss_delta": rss() - before}
            scorers[name] = scorer

        for name, scorer in scorers.items():
            value, times = time_runs(scorer, img)
            out["models"][name].update(score=value, mean_s=sum(times) / len(times), max_s=max(times))

        if len(names) > 1 and scorers:
            t = time.perf_counter()
            for scorer in scorers.values():
                scorer(img)
            out["sequential_s"] = time.perf_counter() - t
    out["rss_after"] = rss()
    out["rss_base"] = base
    out["peak_rss"] = peak_rss()
    return out


def open_image(path: str | None) -> Image.Image:
    if path:
        return Image.open(path).convert("RGB")
    rng = np.random.default_rng(0)
    return Image.fromarray(rng.integers(0, 256, (1024, 1024, 3), dtype=np.uint8))


def run_worker(names: list[str], image: str | None) -> dict:
    cmd = [sys.executable, __file__, "--_worker", ",".join(names)] + ([image] if image else [])
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    if p.returncode != 0:
        return {"crash": (p.stderr or p.stdout).strip().splitlines()[-1:]}
    if p.stderr.strip():
        print(p.stderr.strip(), file=sys.stderr)
    return json.loads(p.stdout.strip().splitlines()[-1])


def gb(n) -> str:
    return "-" if n is None else f"{n / 2**30:.2f}GB"


def cpu_name() -> str:
    if platform.system() == "Windows":
        try:
            return subprocess.run(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"],
                capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:
            pass
    return platform.processor() or platform.machine()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("image", nargs="?", help="입력 이미지 (없으면 임의의 1024x1024)")
    p.add_argument("--models", default=",".join(ALL_MODELS))
    p.add_argument("--_worker", help=argparse.SUPPRESS)
    args = p.parse_args()

    if args._worker:
        print(json.dumps(worker(args._worker.split(","), args.image)))
        return

    names = args.models.split(",")
    img = open_image(args.image)
    print(f"측정일 {time.strftime('%Y-%m-%d')} | CPU {cpu_name()} | 코어 {psutil.cpu_count(False)}/{psutil.cpu_count()} "
          f"| RAM {gb(psutil.virtual_memory().total)} | torch {torch.__version__} (threads {torch.get_num_threads()})")
    print(f"입력: {args.image or '임의 이미지'} {img.size[0]}x{img.size[1]}\n")

    print("| 모델 | 로드 시간 | RSS 증가 | 프로세스 최대 RSS | 추론 평균 | 추론 최대 | 원점수 |")
    print("|---|---|---|---|---|---|---|")
    for name in names:
        r = run_worker([name], args.image)
        m = r.get("models", {}).get(name, {})
        if "crash" in r or "error" in m:
            print(f"| {name} | 실패: {r.get('crash') or m.get('error')} | | | | | |")
            continue
        print(f"| {name} | {m['load_s']:.1f}s | {gb(m['rss_delta'])} | {gb(r['peak_rss'])} "
              f"| {m['mean_s']:.2f}s | {m['max_s']:.2f}s | {m['score']:.4f} |")

    if len(names) > 1:
        r = run_worker(names, args.image)
        if "crash" in r:
            print(f"\n함께 로드: 실패 {r['crash']}")
        else:
            loaded = [n for n, m in r["models"].items() if "error" not in m]
            print(f"\n함께 로드 ({', '.join(loaded)}): RSS {gb(r['rss_after'])} "
                  f"(시작 시 {gb(r['rss_base'])}), 프로세스 최대 RSS {gb(r['peak_rss'])}, "
                  f"순차 추론 {r['sequential_s']:.2f}s")


if __name__ == "__main__":
    main()
