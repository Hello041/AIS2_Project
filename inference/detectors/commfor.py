"""Community Forensics (Park & Owens, CVPR 2025, "Community Forensics: Using Thousands of Generators to Train
Fake Image Detectors").

공식 저장소: https://github.com/JeongsooP/Community-Forensics (커밋 ee5b71d), MIT 라이선스.
가중치: Hugging Face OwensLab/commfor-model-384 (MIT) — model.safetensors, config.json.
  - 모델: models.py ViTClassifier(model_size="small", input_size=384, patch_size=16)
      = timm vit_small_patch16_384, head를 Linear(384 → 1)로 교체.
  - 전처리: dataloader.py get_transform(mode="test") = Resize(440) → CenterCrop(384) → ToTensor → ImageNet 정규화.
  - 출력: 로짓 1개. 학습 라벨 real=0, fake=1 (README 'real:0,fake:1'), 공식 예제는 sigmoid → 클수록 AI.

가중치 위치: inference/weights/commfor/{config.json, model.safetensors} (87MB)
UnivFD 대체 후보로 시험 중 (2026-11-14). 활성 여부는 DETECTORS로 정한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import torch
from PIL import Image

from .base import Detector

INFERENCE = Path(__file__).resolve().parents[1]
WEIGHTS = INFERENCE / "weights" / "commfor"

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
RESIZE, CROP = 440, 384   # 공식 determine_resize_crop_sizes(input_size=384)


def _missing(path: Path) -> FileNotFoundError:
    return FileNotFoundError(
        f"{path} 가 없습니다. Hugging Face OwensLab/commfor-model-384에서 config.json, model.safetensors를 "
        f"{WEIGHTS}에 받으세요 (inference/README.md 참고)."
    )


class CommForDetector(Detector):
    name = "commfor"

    def __init__(self) -> None:
        super().__init__()
        self._model = None
        self._transform = None

    def _load(self) -> None:
        import timm
        from safetensors.torch import load_file
        from torchvision import transforms

        config, weights = WEIGHTS / "config.json", WEIGHTS / "model.safetensors"
        for p in (config, weights):
            if not p.exists():
                raise _missing(p)
        cfg = json.loads(config.read_text(encoding="utf-8"))
        expected = {"model_size": "small", "input_size": 384, "patch_size": 16}
        if {k: cfg.get(k) for k in expected} != expected:
            raise ValueError(f"예상과 다른 설정: {cfg}")

        # pretrained=False: ImageNet 가중치를 인터넷에서 받지 않는다. 전부 체크포인트로 덮는다.
        model = timm.create_model("vit_small_patch16_384", pretrained=False, num_classes=1)
        state = {k.removeprefix("vit."): v for k, v in load_file(str(weights)).items()}
        model.load_state_dict(state, strict=True)
        self._model = model.eval()
        self._transform = transforms.Compose([
            transforms.Resize(RESIZE),
            transforms.CenterCrop(CROP),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])

    @torch.inference_mode()
    def _score(self, img: Image.Image) -> float:
        return torch.sigmoid(self._model(self._transform(img).unsqueeze(0)))[0, 0].item()
