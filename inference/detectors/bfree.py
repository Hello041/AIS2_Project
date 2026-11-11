"""B-Free (Guillaro et al., CVPR 2025, "A Bias-Free Training Paradigm for More General AI-generated Image Detection").

공식 저장소: https://github.com/grip-unina/B-Free (커밋 c6a9f89)
  라이선스: GRIP-UNINA — 정보·비영리 목적만, 저작권 표시 유지, 결과 공개 시 원저자 인용 필수.
  - 모델: code/networks/__init__.py get_network("timm_c5i504_vit_base_patch14_reg4_dinov2.lvd142m")
      = timm ViT-B/14 DINOv2 + 레지스터 4개, Wrapper5crops(504): 504×504 크기 5곳(가운데+네 모서리) 평균.
      504보다 작은 이미지는 모델 안에서 반복해 채운다.
  - 전처리: code/main_bfree_single.py — get_list_norm("resnet") = ToTensor + ImageNet 정규화. Resize·Crop 없음.
  - 출력: 로짓 1개, 양수 = AI (데모 이미지 라벨로 확인) → sigmoid로 0~1, 클수록 AI.

가중치: inference/weights/bfree/BFREE_dino2reg4/{config.yaml, model_epoch_best.pth} (330MB)
공식 코드: inference/third_party/bfree/  (둘 다 scripts/download_weights.py --only bfree로 받는다)
요구: timm>=1.0.12. CPU에서 이미지 크기와 무관하게 약 12초, 상주 약 0.36GB.

2026-11-10 NPR을 대체 (NPR은 PNG/JPEG 형식에 반응해 AUC 0.43 — 계획서 §7 '11/10 점검 결과').
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import torch
import yaml
from PIL import Image

from .base import Detector

INFERENCE = Path(__file__).resolve().parents[1]
WEIGHTS = INFERENCE / "weights" / "bfree" / "BFREE_dino2reg4"
NETWORKS = INFERENCE / "third_party" / "bfree" / "code" / "networks"

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
_PKG = "bfree_official_networks"  # NPR 저장소의 'networks'와 이름이 겹치지 않게


def _missing(path: Path) -> FileNotFoundError:
    return FileNotFoundError(
        f"{path} 가 없습니다. `python inference/scripts/download_weights.py --only bfree`로 받으세요 "
        "(inference/README.md 참고)."
    )


def _import_networks():
    """code/networks 패키지(상대 import 사용)를 고유한 이름으로 불러온다."""
    init = NETWORKS / "__init__.py"
    if not init.exists():
        raise _missing(init)
    if _PKG not in sys.modules:
        spec = importlib.util.spec_from_file_location(_PKG, init, submodule_search_locations=[str(NETWORKS)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[_PKG] = module
        spec.loader.exec_module(module)
    return sys.modules[_PKG]


class BFreeDetector(Detector):
    name = "bfree"

    def __init__(self) -> None:
        super().__init__()
        self._model = None
        self._transform = None

    def _load(self) -> None:
        from torchvision import transforms
        config = WEIGHTS / "config.yaml"
        if not config.exists():
            raise _missing(config)
        cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
        weights = WEIGHTS / cfg["weights_file"]
        if not weights.exists():
            raise _missing(weights)
        if cfg["norm_type"] != "resnet":
            raise ValueError(f"예상과 다른 정규화: {cfg['norm_type']!r} (resnet이어야 함)")

        networks = _import_networks()
        model = networks.get_network(cfg["arch"])  # pretrained=False: 인터넷에서 받지 않는다
        self._model = networks.load_weights(model, str(weights)).eval()
        self._transform = transforms.Compose([
            transforms.ToTensor(), transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])

    def logit(self, img: Image.Image) -> float:
        """공식 출력(로짓) 그대로 — 공식 데모 결과와 비교할 때 쓴다."""
        with torch.inference_mode():
            return self._model(self._transform(img).unsqueeze(0))[0, 0].item()

    @torch.inference_mode()
    def _score(self, img: Image.Image) -> float:
        return torch.sigmoid(self._model(self._transform(img).unsqueeze(0)))[0, 0].item()
