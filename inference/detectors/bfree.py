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
요구: timm>=1.0.12. CPU에서 이미지 크기와 무관하게 약 12초, 상주 약 0.36GB. GPU는 DEVICE 환경 변수(base.resolve_device).

2026-11-10 NPR을 대체 (NPR은 PNG/JPEG 형식에 반응해 AUC 0.43 — 계획서 §7 '11/10 점검 결과').
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path

import numpy as np
import torch
import yaml
from PIL import Image

from .base import Detector, Explanation

log = logging.getLogger("inference")

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


def crop_cells(grid_h: int, grid_w: int, crop: tuple[int, int], replicate_wrap) -> list[np.ndarray]:
    """Wrapper5crops.forward가 하는 자르기를 '격자 번호표'에 그대로 적용한다.

    반환: 다섯 영역(가운데, 왼위, 왼아래, 오른아래, 오른위 — 공식 코드의 순서) 각각에 대해
    crop 크기 격자의 각 칸이 원래 이미지 격자의 몇 번째 칸(행 우선 평탄화 번호)인지.
    504보다 작은 이미지의 반복 채움(replicate_wrap)과 한쪽만 작은 경우의 잘림까지 공식 코드와 같다.
    """
    e = torch.arange(grid_h * grid_w, dtype=torch.int64).reshape(1, 1, grid_h, grid_w)
    ph, pw = max(crop[0] - e.shape[-2], 0), max(crop[1] - e.shape[-1], 0)
    if ph > 0 or pw > 0:
        e = replicate_wrap(e, crop)
    hs = max((e.shape[-2] - crop[0]) // 2, 0)
    ws = max((e.shape[-1] - crop[1]) // 2, 0)
    crops = [
        e[:, :, hs:crop[0] + hs, ws:crop[1] + ws],
        e[:, :, :crop[0], :crop[1]],
        e[:, :, -crop[0]:, :crop[1]],
        e[:, :, -crop[0]:, -crop[1]:],
        e[:, :, :crop[0], -crop[1]:],
    ]
    return [c[0, 0].numpy() for c in crops]


def rollout(attentions: list[torch.Tensor], cls_index: int = 0) -> torch.Tensor:
    """Attention Rollout (Abnar & Zuidema, 2020): 층별 (헤드 평균) 어텐션에 잔차 연결을 반영해
    누적하고, CLS 토큰이 각 토큰에서 받아 온 정보의 비중을 구한다. 반환 (B, N).

    Â_l = 0.5·A_l + 0.5·I (행 합 1 유지), R = Â_L ⋯ Â_1 의 CLS 행 = e_clsᵀ Â_L ⋯ Â_1.
    전체 행렬곱 대신 CLS 행 벡터만 뒤에서부터 곱한다(같은 결과, 계산량 N배 적음).
    """
    b, n, _ = attentions[0].shape
    v = torch.zeros(b, 1, n, dtype=attentions[0].dtype, device=attentions[0].device)
    v[:, 0, cls_index] = 1.0
    for a in reversed(attentions):
        v = 0.5 * (v @ a) + 0.5 * v
    return v[:, 0, :]


class BFreeDetector(Detector):
    name = "bfree"
    supports_explanation = True

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
        self._model = networks.load_weights(model, str(weights)).eval().to(self.device)
        self._transform = transforms.Compose([
            transforms.ToTensor(), transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])

    def logit(self, img: Image.Image) -> float:
        """공식 출력(로짓) 그대로 — 공식 데모 결과와 비교할 때 쓴다."""
        with torch.inference_mode():
            return self._model(self._input(img))[0, 0].item()

    def _input(self, img: Image.Image) -> torch.Tensor:
        """전처리는 CPU, 모델 입력만 self.device로."""
        return self._transform(img).unsqueeze(0).to(self.device)

    @torch.inference_mode()
    def _score(self, img: Image.Image) -> float:
        return torch.sigmoid(self._model(self._input(img)))[0, 0].item()

    # ---------------------------------------------------------------- 모델 주목 영역 (히트맵)
    def _score_and_explain(self, img: Image.Image) -> tuple[float, Explanation | None]:
        """_score와 같은 추론 한 번으로 원점수와 Attention Rollout을 얻는다.

        모델 설정(빠른 어텐션 포함)은 바꾸지 않는다. 각 블록 attn.qkv의 출력을 forward hook으로 **읽기만**
        하고(반환값 None → 모델 계산에 영향 없음), timm Attention의 비융합 경로와 같은 식
        softmax((q·scale) @ kᵀ)로 어텐션을 따로 계산해 헤드 평균을 모은다. 따라서 원점수는 _score와 같다.
        hook 안의 오류·메모리 부족은 삼키고 주목 영역만 None으로 둔다(판정은 계속).
        """
        vit = self._model.model  # Wrapper5crops 안의 timm VisionTransformer
        blocks = list(vit.blocks)
        collected: list[torch.Tensor] = []
        ok = [True]

        def make_hook(attn):
            def hook(_module, _inputs, output):
                if not ok[0]:
                    return None
                try:
                    b, n, _c = output.shape
                    qkv = output.reshape(b, n, 3, attn.num_heads, attn.head_dim).permute(2, 0, 3, 1, 4)
                    q, k = attn.q_norm(qkv[0]), attn.k_norm(qkv[1])
                    mean = None
                    for h in range(attn.num_heads):  # 헤드별로 계산해 순간 메모리를 줄인다
                        a = ((q[:, h] * attn.scale) @ k[:, h].transpose(-2, -1)).softmax(dim=-1)
                        mean = a if mean is None else mean.add_(a)
                    collected.append(mean.div_(attn.num_heads))
                except Exception:  # noqa: BLE001 — 주목 영역 실패가 판정을 막으면 안 된다
                    ok[0] = False
                    collected.clear()
                return None

            return hook

        handles = [blk.attn.qkv.register_forward_hook(make_hook(blk.attn)) for blk in blocks]
        try:
            with torch.inference_mode():
                logit = self._model(self._input(img))
        finally:
            for h in handles:
                h.remove()
        score = torch.sigmoid(logit)[0, 0].item()

        explanation = None
        if ok[0] and len(collected) == len(blocks):
            try:
                explanation = self._explain_from_attention(collected, img.size)
            except Exception:  # noqa: BLE001
                log.exception("bfree explanation failed")
        else:
            log.warning("bfree attention not collected")
        collected.clear()
        return score, explanation

    def _explain_from_attention(self, attentions: list[torch.Tensor], size: tuple[int, int]) -> Explanation:
        """다섯 영역의 Rollout(36×36 패치)을 원래 이미지의 패치 격자 위치로 되돌려 놓는다.

        같은 칸을 여러 영역이 보면 평균한다(최종 로짓도 다섯 영역의 평균). 어느 영역도 보지 않은 칸은 NaN.
        """
        pe = self._model.patch_embed
        cell = int(pe.proj.stride[0])
        crop = tuple(int(g) for g in pe.grid_size)  # (36, 36)
        width, height = size
        grid_h, grid_w = height // cell, width // cell  # 스트라이드 14, 패딩 없는 conv의 출력 크기
        rep = importlib.import_module(f"{_PKG}.wrapper5crops").replicate_wrap

        with torch.inference_mode():
            weights = rollout(attentions, cls_index=0)  # (5, N), timm 토큰 순서 [CLS, 레지스터 4, 패치]
        patches = weights[:, self._model.model.num_prefix_tokens:].float().cpu().numpy()
        # 영역마다 CLS·레지스터로 간 비중이 달라 척도가 다르다 → 패치끼리의 상대 비중(합 1)으로 맞춘 뒤 합친다
        patches = patches / np.maximum(patches.sum(axis=1, keepdims=True), 1e-12)
        cells = crop_cells(grid_h, grid_w, crop, rep)
        if patches.shape != (len(cells), crop[0] * crop[1]):
            raise ValueError(f"예상과 다른 어텐션 크기: {patches.shape}")

        sums = np.zeros(grid_h * grid_w)
        counts = np.zeros(grid_h * grid_w)
        for k, idx in enumerate(cells):
            np.add.at(sums, idx.ravel(), patches[k])
            np.add.at(counts, idx.ravel(), 1)
        values = np.full(grid_h * grid_w, np.nan)
        seen = counts > 0
        values[seen] = sums[seen] / counts[seen]
        return Explanation(values=values.reshape(grid_h, grid_w), cell=cell, method="attention_rollout")
