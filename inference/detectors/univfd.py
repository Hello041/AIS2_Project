"""UnivFD (Ojha et al., CVPR 2023) — CLIP ViT-L/14 이미지 인코더 + 선형 분류층.

공식 저장소: https://github.com/WisconsinAIVision/UniversalFakeDetect (커밋 030495a, MIT)
  - 모델: models/clip_models.py — CLIP.encode_image → nn.Linear(768, 1)
  - 백본 구현: models/clip/model.py (OpenAI CLIP 복사본)의 VisionTransformer
  - 전처리: validate.py — CenterCrop(224) → ToTensor → CLIP 정규화 (Resize 없음)
  - 출력: validate.py에서 model(x).sigmoid() — 로짓 1개, 양수 = fake. 그대로 sigmoid → 0~1, 클수록 AI.

CLAUDE.md 규칙에 따라 **이미지 인코더만** 만든다. OpenAI ViT-L-14.pt(TorchScript)에서 visual.* 가중치만
골라 VisionTransformer에 올리고, 텍스트 인코더는 만들지 않는다.

가중치: inference/weights/univfd/{ViT-L-14.pt, fc_weights.pth}
공식 코드: inference/third_party/univfd/  (둘 다 scripts/download_weights.py로 받는다)

전처리 모드 (환경 변수 UNIVFD_PREPROCESS):
  - "crop"  (기본): 공식 평가 코드 그대로. CenterCrop 224 — 큰 사진은 가운데 224×224만 본다.
  - "resize": CLIP 기본 전처리. Resize 224(bicubic, 짧은 변) → CenterCrop 224 — 사진 전체를 본다.
"""
from __future__ import annotations

import gc
import importlib.util
import os
from pathlib import Path

import torch
from PIL import Image

from .base import Detector

INFERENCE = Path(__file__).resolve().parents[1]
WEIGHTS = INFERENCE / "weights" / "univfd"
CLIP_MODEL_PY = INFERENCE / "third_party" / "univfd" / "models" / "clip" / "model.py"

# models/clip/clip.py의 _transform과 같은 값
CLIP_MEAN = (0.48145466, 0.4578275, 0.40821073)
CLIP_STD = (0.26862954, 0.26130258, 0.27577711)
INPUT_SIZE = 224
PREPROCESS_MODES = ("crop", "resize")


def _missing(path: Path) -> FileNotFoundError:
    return FileNotFoundError(
        f"{path} 가 없습니다. `python inference/scripts/download_weights.py --only univfd`로 받으세요 "
        "(inference/README.md 참고)."
    )


def _load_clip_model_module():
    """공식 저장소의 models/clip/model.py를 파일 경로로 읽는다.
    (저장소마다 'models' 패키지 이름이 겹쳐서 sys.path로 import하지 않는다)"""
    if not CLIP_MODEL_PY.exists():
        raise _missing(CLIP_MODEL_PY)
    spec = importlib.util.spec_from_file_location("univfd_clip_model", CLIP_MODEL_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_transform(mode: str):
    from torchvision import transforms
    if mode not in PREPROCESS_MODES:
        raise ValueError(f"UNIVFD_PREPROCESS는 {PREPROCESS_MODES} 중 하나여야 합니다: {mode!r}")
    steps = []
    if mode == "resize":
        steps.append(transforms.Resize(INPUT_SIZE, interpolation=transforms.InterpolationMode.BICUBIC))
    steps += [transforms.CenterCrop(INPUT_SIZE), transforms.ToTensor(), transforms.Normalize(CLIP_MEAN, CLIP_STD)]
    return transforms.Compose(steps)


class UnivFDDetector(Detector):
    name = "univfd"

    def __init__(self, preprocess: str | None = None) -> None:
        super().__init__()
        self.preprocess = preprocess or os.environ.get("UNIVFD_PREPROCESS", "crop")
        self._transform = build_transform(self.preprocess)  # 잘못된 값이면 load 전에 바로 오류
        self._visual = None
        self._fc = None

    def _load(self) -> None:
        clip_pt, fc_pt = WEIGHTS / "ViT-L-14.pt", WEIGHTS / "fc_weights.pth"
        for p in (clip_pt, fc_pt):
            if not p.exists():
                raise _missing(p)
        clip_model = _load_clip_model_module()

        jit = torch.jit.load(str(clip_pt), map_location="cpu")
        full = jit.state_dict()
        del jit
        sd = {k[len("visual."):]: v for k, v in full.items() if k.startswith("visual.")}
        del full
        gc.collect()

        # models/clip/model.py의 build_model()과 같은 방식으로 구조 값을 가중치에서 읽는다
        width = sd["conv1.weight"].shape[0]
        patch = sd["conv1.weight"].shape[-1]
        layers = len({k.split(".")[2] for k in sd if k.startswith("transformer.resblocks.")})
        grid = round((sd["positional_embedding"].shape[0] - 1) ** 0.5)
        visual = clip_model.VisionTransformer(
            input_resolution=patch * grid, patch_size=patch, width=width,
            layers=layers, heads=width // 64, output_dim=sd["proj"].shape[1],
        )
        visual.load_state_dict(sd)  # strict
        self._visual = visual.float().eval()

        fc = torch.nn.Linear(sd["proj"].shape[1], 1)
        fc.load_state_dict(torch.load(fc_pt, map_location="cpu"))  # strict
        self._fc = fc.eval()

    @torch.inference_mode()
    def _score(self, img: Image.Image) -> float:
        x = self._transform(img).unsqueeze(0)
        return torch.sigmoid(self._fc(self._visual(x)))[0, 0].item()
