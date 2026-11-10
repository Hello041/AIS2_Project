"""이미지 변형 (검증 데이터의 변형 버전 + Sprint 2 판정 안정성에서 같은 함수를 쓴다).

계획서 §5.3(MVP: 원본 + JPEG 70), §12.4·기획서 §7-5(최종: JPEG 70, Resize 50%, Screenshot 모사 = 축소 후 PNG).
세부 설정(리샘플링 필터, 스크린샷 크기)은 계획서에 없어 2026-11-10에 아래 값으로 정했다. 바꾸면 변형을 다시 만들고
점수·경계값을 다시 구해야 한다.

모든 함수는 순수 함수다: 입력 이미지를 바꾸지 않고, 디스크·네트워크를 쓰지 않는다(메모리에서만 인코딩).
"""
from __future__ import annotations

import io

from PIL import Image

# ---------------------------------------------------------------- 설정 (한 곳에서만 정의)
JPEG70_QUALITY = 70
JPEG_SUBSAMPLING = 2               # 4:2:0 (Pillow 기본, 일반 JPEG와 같음)
RESIZE50_SCALE = 0.5
RESIZE50_FILTER = Image.BICUBIC
SCREENSHOT_LONG_SIDE = 1080        # 휴대폰 화면 가로 해상도(FHD)에 맞춰 표시한 뒤 캡처했다고 가정
SCREENSHOT_FILTER = Image.BILINEAR # 화면 표시 시 일반적인 보간

VERSIONS = ("jpeg70", "resize50", "screenshot")
EXTENSIONS = {"jpeg70": "jpg", "resize50": "png", "screenshot": "png"}
DESCRIPTIONS = {
    "jpeg70": f"JPEG q{JPEG70_QUALITY} 4:2:0 재압축",
    "resize50": f"가로·세로 {int(RESIZE50_SCALE * 100)}% bicubic 축소, PNG",
    "screenshot": f"긴 변 {SCREENSHOT_LONG_SIDE}px bilinear 축소(이미 작으면 그대로), PNG",
}


def _rgb(img: Image.Image) -> Image.Image:
    return img if img.mode == "RGB" else img.convert("RGB")


def _scaled(size: tuple[int, int], scale: float) -> tuple[int, int]:
    return max(1, round(size[0] * scale)), max(1, round(size[1] * scale))


def encode_variant(img: Image.Image, version: str) -> tuple[bytes, str]:
    """img의 변형을 파일 바이트와 확장자로 반환한다. EXIF 등 메타데이터는 넣지 않는다."""
    if version not in VERSIONS:
        raise ValueError(f"version은 {VERSIONS} 중 하나: {version!r}")
    img = _rgb(img)
    buf = io.BytesIO()
    if version == "jpeg70":
        img.save(buf, "JPEG", quality=JPEG70_QUALITY, subsampling=JPEG_SUBSAMPLING)
    elif version == "resize50":
        img.resize(_scaled(img.size, RESIZE50_SCALE), RESIZE50_FILTER).save(buf, "PNG")
    else:  # screenshot
        scale = min(1.0, SCREENSHOT_LONG_SIDE / max(img.size))
        out = img if scale == 1.0 else img.resize(_scaled(img.size, scale), SCREENSHOT_FILTER)
        out.save(buf, "PNG")
    return buf.getvalue(), EXTENSIONS[version]


def make_variant(img: Image.Image, version: str) -> Image.Image:
    """변형한 뒤 다시 디코딩한 이미지 (서버에서 메모리로만 쓸 때)."""
    data, _ = encode_variant(img, version)
    out = Image.open(io.BytesIO(data))
    out.load()
    return out
