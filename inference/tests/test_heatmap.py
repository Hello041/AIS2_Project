"""히트맵(모델 주목 영역) 테스트 — heatmap.py 렌더링과 B-Free 다섯 영역 위치 계산.

- 렌더링 테스트는 모델 없이 돈다.
- 위치 계산은 공식 Wrapper5crops 코드에 '격자 번호표'를 통과시켜 crop_cells와 칸 단위로 같은지 본다.
  공식 코드(third_party/bfree)가 없으면 건너뛴다. 가중치는 필요 없다(무작위 초기화 timm 모델).
"""
import base64
import io

import numpy as np
import pytest
import torch
from PIL import Image, ImageOps

import heatmap
from detectors.base import Explanation
from detectors.bfree import NETWORKS, crop_cells, rollout

HAVE_CODE = (NETWORKS / "wrapper5crops.py").exists()
needs_code = pytest.mark.skipif(not HAVE_CODE, reason="B-Free 공식 코드 없음")


def decode_png(heat):
    return Image.open(io.BytesIO(base64.b64decode(heat["png_base64"])))


def explanation_for(size, cell=14, seen=lambda r, c: True):
    w, h = size
    gh, gw = h // cell, w // cell
    vals = np.random.default_rng(0).random((gh, gw))
    mask = np.array([[seen(r, c) for c in range(gw)] for r in range(gh)])
    return Explanation(values=np.where(mask, vals, np.nan), cell=cell, method="attention_rollout")


# ---------------------------------------------------------------- 렌더링
def test_render_basic_png_and_coverage():
    img = Image.new("RGB", (1258, 834), (90, 120, 60))
    ex = explanation_for(img.size)
    heat = heatmap.render(img, ex, "bfree")
    png = decode_png(heat)
    assert png.format == "PNG" and max(png.size) <= heatmap.MAX_SIDE
    assert (heat["width"], heat["height"]) == png.size
    assert heat["model"] == "bfree" and heat["method"] == "attention_rollout"
    # 격자가 덮는 면적(89×59칸×14²) / 전체 면적 — 오른쪽·아래 자투리는 범위 밖
    assert heat["coverage"] == pytest.approx(89 * 59 * 14 * 14 / (1258 * 834), abs=1e-4)


def test_uncovered_area_is_gray_not_colored():
    """범위 밖 칸은 색(주목도)을 칠하지 않고 무채색(회색 빗금)으로 둔다."""
    img = Image.new("RGB", (700, 700), (200, 40, 40))  # 빨간 원본 → 범위 밖은 회색으로 바뀌어야 함
    ex = explanation_for(img.size, seen=lambda r, c: c < 25)  # 왼쪽 절반만 봄
    arr = np.asarray(decode_png(heatmap.render(img, ex, "bfree")), dtype=int)
    right = arr[:, -100:]  # 오른쪽(범위 밖)
    assert np.abs(right[..., 0] - right[..., 1]).max() <= 2 and np.abs(right[..., 1] - right[..., 2]).max() <= 2
    left = arr[:, :100]
    assert np.abs(left[..., 0] - left[..., 2]).mean() > 10  # 본 영역은 색이 있음


def test_exif_orientation_rotates_output():
    img = Image.new("RGB", (600, 300), (10, 10, 10))
    ex_tag = Image.Exif()
    ex_tag[0x0112] = 6  # 90° 회전해서 보여야 하는 사진
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=ex_tag.tobytes())
    rotated = Image.open(io.BytesIO(buf.getvalue()))
    heat = heatmap.render(rotated, explanation_for(rotated.size), "bfree")
    assert heatmap.orientation(rotated) == 6
    assert heat["height"] > heat["width"]  # 세로로 회전됨


def test_colormap_blue_yellow_red():
    """낮음 = 파랑, 중간 = 노랑, 높음 = 빨강 (검정에 가까운 Turbo 양 끝은 쓰지 않는다)."""
    lo, mid, hi = heatmap.colormap(np.array([0.0, 0.5, 1.0]))
    assert lo[2] > lo[0] + 100 and lo[2] > lo[1] + 50          # 파랑
    assert min(mid[0], mid[1]) > 180 and mid[2] < 80            # 노랑 (R·G 높고 B 낮음)
    assert hi[0] > 150 and hi[0] > hi[1] + 100 and hi[2] < 40   # 빨강
    t = np.linspace(0, 1, 101)
    rgb = heatmap.colormap(t)
    assert rgb.min() >= 0 and rgb.max() <= 255
    assert np.all(rgb.sum(axis=-1) > 150)  # 어디서도 검정에 가깝지 않음 → 원본이 어둡게 덮이지 않음
    assert np.array_equal(heatmap.colormap(np.array([-1.0, 2.0])), heatmap.colormap(np.array([0.0, 1.0])))


@pytest.mark.parametrize("orient", [1, 3, 6, 8])
def test_high_attention_is_red_and_follows_orientation(orient):
    """주목도 높은 칸은 빨강, 낮은 칸은 파랑으로 겹치고, EXIF 회전 후에도 원본과 같은 위치에 있다."""
    w, h, cell = 560, 280, 14
    gh, gw = h // cell, w // cell
    vals = np.full((gh, gw), 0.1)
    vals[: gh // 2, : gw // 4] = 1.0  # 저장 방향 기준 왼쪽 위 구석만 높음
    ex = Explanation(values=vals, cell=cell, method="attention_rollout")
    exif = Image.Exif()
    exif[0x0112] = orient
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (128, 128, 128)).save(buf, "JPEG", exif=exif.tobytes())
    img = Image.open(io.BytesIO(buf.getvalue()))
    arr = np.asarray(decode_png(heatmap.render(img, ex, "bfree")), dtype=int)

    # 같은 위치 표시를 원본에 그려 PIL의 exif_transpose(앱이 원본을 보여 주는 방향)로 돌린 기준
    marker = Image.new("L", (w, h), 0)
    marker.paste(255, (0, 0, w // 4, h // 2))
    marker.info["exif"] = exif.tobytes()
    marker = ImageOps.exif_transpose(marker).resize((arr.shape[1], arr.shape[0]), Image.Resampling.NEAREST)
    m = np.asarray(marker) > 127
    edge = 40  # 표시용 흐림(약 3칸)이 번지는 경계는 빼고 비교
    inner = np.zeros_like(m)
    inner[edge:-edge, edge:-edge] = True
    hot = m & inner & ~np.roll(~m, edge, 0) & ~np.roll(~m, -edge, 0) & ~np.roll(~m, edge, 1) & ~np.roll(~m, -edge, 1)
    cold = ~m & ~np.roll(m, edge, 0) & ~np.roll(m, -edge, 0) & ~np.roll(m, edge, 1) & ~np.roll(m, -edge, 1)
    r, b = arr[..., 0], arr[..., 2]
    assert hot.any() and cold.any()
    assert (r[hot] > b[hot] + 60).all()  # 빨강 쪽
    assert (b[cold] > r[cold] + 30).all()  # 파랑 쪽


@pytest.mark.parametrize("bad", ["shape", "allnan"])
def test_render_rejects_bad_explanation(bad):
    img = Image.new("RGB", (280, 280))
    if bad == "shape":
        ex = Explanation(values=np.ones((3, 3)), cell=14, method="x")
    else:
        ex = Explanation(values=np.full((20, 20), np.nan), cell=14, method="x")
    with pytest.raises(ValueError):
        heatmap.render(img, ex, "bfree")


def test_smooth_keeps_out_of_range_as_nan():
    v = np.ones((10, 10))
    v[:, 5:] = np.nan
    s = heatmap.smooth(v)
    assert np.isnan(s[:, 5:]).all() and np.allclose(s[:, :5], 1.0)


def test_rollout_cls_row_matches_full_product():
    """CLS 행 벡터만 곱하는 구현이 전체 행렬곱(Â_L ⋯ Â_1)의 CLS 행과 같은지."""
    g = torch.Generator().manual_seed(0)
    attns = [torch.softmax(torch.randn(2, 7, 7, generator=g), dim=-1) for _ in range(4)]
    eye = torch.eye(7)
    full = torch.eye(7).expand(2, 7, 7)
    for a in attns:  # 1층부터: R = Â_l R
        full = (0.5 * a + 0.5 * eye) @ full
    assert torch.allclose(rollout(attns, 0), full[:, 0, :], atol=1e-6)


# ---------------------------------------------------------------- 다섯 영역 위치 = 공식 코드
def _official_cells(size):
    """공식 Wrapper5crops.forward에 '번호표 이미지'를 넣어 각 영역이 실제로 받은 격자 칸 번호를 꺼낸다."""
    import timm

    from detectors.bfree import _import_networks

    networks = _import_networks()
    import importlib

    w5 = importlib.import_module(f"{networks.__name__}.wrapper5crops")
    vit = timm.create_model("vit_base_patch14_reg4_dinov2", pretrained=False, num_classes=1)
    wrapper = w5.Wrapper5crops(vit, 504)
    proj = wrapper.patch_embed.proj
    with torch.no_grad():  # 채널 0 = 각 14×14 칸 왼쪽 위 픽셀 값
        proj.weight.zero_()
        proj.bias.zero_()
        proj.weight[0, 0, 0, 0] = 1.0
    captured = {}

    class Capture(torch.nn.Module):
        def forward(self, emb):
            captured["emb"] = emb
            return torch.zeros(emb.shape[0], 1)

    wrapper.model = Capture()
    w, h = size
    gh, gw = h // 14, w // 14
    x = torch.zeros(1, 3, h, w)
    x[0, 0, : gh * 14 : 14, : gw * 14 : 14] = torch.arange(gh * gw, dtype=torch.float32).reshape(gh, gw)
    with torch.no_grad():
        wrapper(x)
    emb = captured["emb"][:, :, 0]  # (5, 1296)
    return [e.round().long().numpy().reshape(36, 36) for e in emb], w5.replicate_wrap, (gh, gw)


@needs_code
@pytest.mark.parametrize("size", [(1258, 834), (835, 1256), (1024, 1024), (300, 200), (2000, 300), (4032, 3024)])
def test_crop_cells_match_official_wrapper(size):
    official, rep, (gh, gw) = _official_cells(size)
    ours = crop_cells(gh, gw, (36, 36), rep)
    for k in range(5):
        np.testing.assert_array_equal(ours[k], official[k])


@needs_code
def test_12mp_coverage_is_five_small_regions():
    """1,200만 화소 사진은 504×504 다섯 곳만 본다 (약 10%)."""
    _, rep, (gh, gw) = _official_cells((4032, 3024))
    cells = crop_cells(gh, gw, (36, 36), rep)
    covered = np.unique(np.concatenate([c.ravel() for c in cells]))
    assert len(covered) == 5 * 36 * 36
    assert len(covered) * 14 * 14 / (4032 * 3024) == pytest.approx(0.1042, abs=1e-3)
