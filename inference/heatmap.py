"""모델 주목 영역(Explanation) → 결과 화면용 PNG (계획서 §12.4).

판정과 무관한 참고 정보다. 이 모듈의 실패는 main.py가 잡아 heatmap: null로 바꾸고, 판정은 그대로 응답한다.

- 원본을 긴 변 MAX_SIDE 이하로 줄이고, 모델이 본 칸에는 주목도를 색(파랑 → 노랑 → 빨강, 이미지 안에서의 상대값)으로 반투명하게 겹친다.
- 모델이 **보지 않은 칸(분석 범위 밖)은 색을 칠하지 않고** 회색 빗금으로 덮는다 → 주목 영역과 섞이지 않게.
- EXIF Orientation을 마지막에 적용해 앱이 보여 주는 원본과 같은 방향으로 만든다.
  (모델 좌표는 디코딩된 저장 방향 기준. Orientation 태그 하나만 읽으며 GPS 등 다른 EXIF는 읽지 않는다.)
- 메모리(BytesIO)에서만 만든다. 파일로 저장하지 않는다.
"""
from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image

from detectors.base import Explanation, to_rgb

MAX_SIDE = 512
ALPHA_MIN, ALPHA_MAX = 0.30, 0.65  # 낮은 곳도 파랗게 보이되 원본 형태가 남고, 높은 곳일수록 색이 진하게
HATCH_PERIOD = 8     # 빗금 간격(px)
BLUR_SIGMA = 1.0     # 표시용 흐림(격자 칸 단위). 모델 값 자체는 바꾸지 않는다
ORIENTATION_TAG = 0x0112

# Turbo 컬러맵 (Google, 2019)의 다항식 근사 — d3-scale-chromatic interpolateTurbo와 같은 계수 (0~255)
# 낮음 = 파랑, 중간 = 노랑, 높음 = 빨강이 되도록 Turbo의 구간만 골라 쓴다 (양 끝의 검정에 가까운 색은 쓰지 않는다).
# 0 → TURBO_LOW(파랑), 0.5 → TURBO_MID(노랑), 1 → TURBO_HIGH(빨강), 사이는 Turbo 곡선을 그대로 따라간다.
TURBO_LOW, TURBO_MID, TURBO_HIGH = 0.12, 0.62, 0.90


def _turbo(s: np.ndarray) -> np.ndarray:
    r = 34.61 + s * (1172.33 - s * (10793.56 - s * (33300.12 - s * (38394.49 - s * 14825.05))))
    g = 23.31 + s * (557.33 + s * (1225.33 - s * (3574.96 - s * (1073.77 + s * 707.56))))
    b = 27.2 + s * (3211.1 - s * (15327.97 - s * (27814 - s * (22569.18 - s * 6838.66))))
    return np.clip(np.stack([r, g, b], axis=-1), 0, 255)


_TRANSPOSE = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}


def orientation(img: Image.Image) -> int:
    """EXIF Orientation(1~8). 없거나 읽을 수 없으면 1."""
    try:
        value = int(img.getexif().get(ORIENTATION_TAG, 1))
    except Exception:  # noqa: BLE001 — 깨진 EXIF는 회전 없음으로 본다
        return 1
    return value if value in _TRANSPOSE or value == 1 else 1


def colormap(t: np.ndarray) -> np.ndarray:
    """0~1(이미지 안에서의 상대적인 주목 정도) → RGB (… × 3). 파랑 → 노랑 → 빨강."""
    t = np.clip(np.asarray(t, dtype=float), 0, 1)
    s = np.interp(t, [0.0, 0.5, 1.0], [TURBO_LOW, TURBO_MID, TURBO_HIGH])
    return _turbo(s)


def smooth(values: np.ndarray, sigma: float = BLUR_SIGMA) -> np.ndarray:
    """NaN(범위 밖)을 무시하는 가우시안 흐림 (정규화 합성곱). 범위 밖 칸은 NaN 그대로 둔다.

    표시할 때 패치 경계·단일 토큰 반점을 누그러뜨리기 위한 것. 본 칸들의 값만 섞이고 범위 밖으로 번지지 않는다.
    """
    if sigma <= 0:
        return values
    r = max(1, int(round(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    mask = ~np.isnan(values)
    v = np.where(mask, values, 0.0)
    m = mask.astype(float)

    def conv(a: np.ndarray) -> np.ndarray:
        a = np.apply_along_axis(lambda row: np.convolve(row, k, mode="same"), 1, a)
        return np.apply_along_axis(lambda col: np.convolve(col, k, mode="same"), 0, a)

    num, den = conv(v), conv(m)
    out = np.where(mask & (den > 1e-12), num / np.maximum(den, 1e-12), np.nan)
    return out


def _small_size(width: int, height: int) -> tuple[int, int]:
    scale = min(1.0, MAX_SIDE / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def render(img: Image.Image, explanation: Explanation, model: str) -> dict:
    """주목 영역을 겹친 PNG(base64)와 분석 범위 비율을 만든다.

    반환: {"model", "method", "png_base64", "coverage"(0~1, 원본 면적 중 모델이 본 비율), "width", "height"}
    width·height는 PNG(EXIF 회전 적용 후) 크기.
    """
    width, height = img.size
    values = smooth(np.asarray(explanation.values, dtype=float))
    cell = int(explanation.cell)
    grid_h, grid_w = values.shape
    if cell <= 0 or grid_h != height // cell or grid_w != width // cell:
        raise ValueError(f"격자 크기가 이미지와 맞지 않습니다: {values.shape}, cell={cell}, image={img.size}")

    seen = ~np.isnan(values)
    if not seen.any():
        raise ValueError("모델이 본 칸이 없습니다")
    coverage = float(seen.sum()) * cell * cell / float(width * height)

    # 원본 축소 (큰 사진은 reduce로 먼저 줄여 메모리·시간 절약)
    sw, sh = _small_size(width, height)
    rgb = to_rgb(img)
    factor = max(1, min(width // sw, height // sh) // 2)
    if factor > 1:
        rgb = rgb.reduce(factor)
    base = np.asarray(rgb.resize((sw, sh), Image.Resampling.BILINEAR), dtype=float)

    # 작은 이미지의 각 픽셀 → 원본 좌표 → 격자 칸 (가장 가까운 칸, 격자 밖은 범위 밖)
    ys = ((np.arange(sh) + 0.5) * height / sh // cell).astype(int)
    xs = ((np.arange(sw) + 0.5) * width / sw // cell).astype(int)
    inside = (ys[:, None] < grid_h) & (xs[None, :] < grid_w)
    yc, xc = np.minimum(ys, grid_h - 1), np.minimum(xs, grid_w - 1)
    cell_vals = values[yc[:, None], xc[None, :]]
    covered = inside & ~np.isnan(cell_vals)

    # 정규화: 본 칸들의 2~98 백분위로 0~1 (이미지마다 상대값 — 절대적인 'AI 정도'가 아님)
    seen_vals = values[seen]
    lo, hi = np.percentile(seen_vals, [2, 98])
    t = np.clip((cell_vals - lo) / (hi - lo), 0, 1) if hi - lo > 1e-12 else np.full(cell_vals.shape, 0.5)
    t = np.where(covered, t, 0.0)

    out = np.empty_like(base)
    alpha = (ALPHA_MIN + (ALPHA_MAX - ALPHA_MIN) * t)[..., None]
    blend = (1 - alpha) * base + alpha * colormap(t)
    gray = base.mean(axis=-1, keepdims=True) * 0.25 + 150  # 밝은 회색으로 눌러 원본 형태만 흐리게
    yy, xx = np.indices((sh, sw))
    hatch = ((xx + yy) % HATCH_PERIOD) < 2
    uncovered = np.where(hatch[..., None], gray - 45, gray)
    out[:] = np.where(covered[..., None], blend, uncovered)

    result = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")
    o = orientation(img)
    if o in _TRANSPOSE:
        result = result.transpose(_TRANSPOSE[o])

    buf = io.BytesIO()
    result.save(buf, "PNG", optimize=True)
    return {
        "model": model,
        "method": explanation.method,
        "png_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
        "coverage": round(coverage, 4),
        "width": result.width,
        "height": result.height,
    }
