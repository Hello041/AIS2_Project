"""AIDE (Yan et al., ICLR 2025, "A Sanity Check for AI-generated Image Detection").

공식 저장소: https://github.com/shilinyan99/AIDE (커밋 6725b71, MIT)
  - 모델: models/AIDE.py — AIDE_Model(resnet_path, convnext_path)
      DCT 최고·최저 주파수 패치 4개 → HPF + ResNet-50 두 개, 원본 → open_clip ConvNeXt-XXL, 둘을 이어 MLP(2 클래스)
  - 전처리: data/datasets.py TestDataset — ToTensor → DCT_base_Rec_Module(data/dct.py)로 패치 4개
      → 패치 4개와 원본 각각 Resize([256, 256]) + ImageNet 정규화 → [minmin, maxmax, minmin1, maxmax1, 원본] 순으로 쌓음
  - 출력: 2-클래스 로짓. 라벨은 0_real = 0, 1_fake = 1 (TestDataset) → softmax의 1번(=AI) 값을 원점수로 쓴다.

가중치: inference/weights/aide/sd14_train.pth (SD1.4 학습, 3.35GB)
  체크포인트에 ConvNeXt-XXL·ResNet 백본까지 모두 들어 있어 resnet_path·convnext_path는 None으로 두고
  체크포인트를 strict로 올린다 (2026-11-04 키 전부 일치 확인).
공식 코드: inference/third_party/aide/  (둘 다 scripts/download_weights.py로 받는다)

메모리: 상주 약 3.4GB, 로드 순간 최대 약 7GB (무작위 초기화 모델 + 체크포인트가 동시에 메모리에 있음).
"""
from __future__ import annotations

import gc
import importlib
import importlib.util
import sys
import types
from pathlib import Path

import torch
from PIL import Image

from .base import Detector

INFERENCE = Path(__file__).resolve().parents[1]
WEIGHTS = INFERENCE / "weights" / "aide"
CHECKPOINT = WEIGHTS / "sd14_train.pth"
REPO = INFERENCE / "third_party" / "aide"

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
VIEW_SIZE = 256        # datasets.py transform_train: Resize([256, 256])
MIN_SIDE = 32          # dct.py DCT_base_Rec_Module(window_size=32): 이보다 작은 변은 패치를 못 자른다
_PKG = "aide_official_models"  # 다른 저장소의 'models' 패키지와 이름이 겹치지 않게


def _missing(path: Path) -> FileNotFoundError:
    return FileNotFoundError(
        f"{path} 가 없습니다. `python inference/scripts/download_weights.py --only aide`로 받으세요 "
        "(AIDE는 Google Drive 한도로 실패할 수 있음 — inference/README.md 참고)."
    )


def _import_official():
    """models/AIDE.py(상대 import 사용)와 data/dct.py를 고유한 이름으로 불러온다."""
    models_dir, dct_py = REPO / "models", REPO / "data" / "dct.py"
    for p in (models_dir / "AIDE.py", dct_py):
        if not p.exists():
            raise _missing(p)
    if _PKG not in sys.modules:
        pkg = types.ModuleType(_PKG)
        pkg.__path__ = [str(models_dir)]  # models/에 __init__.py가 없어서 패키지를 직접 만든다
        sys.modules[_PKG] = pkg
    aide_module = importlib.import_module(f"{_PKG}.AIDE")

    # data/__init__.py는 설치하지 않은 kornia를 끌어오므로 dct.py만 파일로 읽는다
    spec = importlib.util.spec_from_file_location("aide_official_dct", dct_py)
    dct_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dct_module)
    return aide_module, dct_module


class AIDEDetector(Detector):
    name = "aide"

    def __init__(self) -> None:
        super().__init__()
        self._model = None
        self._dct = None
        self._to_tensor = None
        self._post = None

    def _load(self) -> None:
        from torchvision import transforms
        if not CHECKPOINT.exists():
            raise _missing(CHECKPOINT)
        aide_module, dct_module = _import_official()

        model = aide_module.AIDE(resnet_path=None, convnext_path=None)
        ckpt = torch.load(CHECKPOINT, map_location="cpu")
        model.load_state_dict(ckpt.get("model", ckpt), strict=True)
        del ckpt
        gc.collect()
        self._model = model.eval()
        self._dct = dct_module.DCT_base_Rec_Module()

        self._to_tensor = transforms.ToTensor()
        # antialias=None: torchvision 0.15 텐서 Resize의 기본 동작 = 공식 코드와 같음
        self._post = transforms.Compose([
            transforms.Resize([VIEW_SIZE, VIEW_SIZE], antialias=None),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])

    @staticmethod
    def _ensure_min_side(img: Image.Image) -> Image.Image:
        """짧은 변이 32px 미만이면 DCT가 실패하므로 비율을 유지해 32px로 키운다 (공식 코드에는 없는 처리)."""
        w, h = img.size
        if min(w, h) >= MIN_SIDE:
            return img
        s = MIN_SIDE / min(w, h)
        return img.resize((max(MIN_SIDE, round(w * s)), max(MIN_SIDE, round(h * s))), Image.BICUBIC)

    @torch.inference_mode()
    def _score(self, img: Image.Image) -> float:
        x = self._to_tensor(self._ensure_min_side(img))
        minmin, maxmax, minmin1, maxmax1 = self._dct(x)
        views = [self._post(v) for v in (minmin, maxmax, minmin1, maxmax1, x)]
        logits = self._model(torch.stack(views).unsqueeze(0))
        return torch.softmax(logits, dim=1)[0, 1].item()  # 1 = fake
