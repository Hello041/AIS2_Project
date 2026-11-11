"""inference/variants.py 테스트."""
import io

import numpy as np
import pytest
from PIL import Image

import variants


@pytest.fixture
def img():
    rng = np.random.default_rng(0)
    return Image.fromarray(rng.integers(0, 256, (896, 1152, 3), dtype=np.uint8))


def test_jpeg70(img):
    data, ext = variants.encode_variant(img, "jpeg70")
    out = Image.open(io.BytesIO(data))
    assert ext == "jpg" and out.format == "JPEG" and out.size == img.size
    # 품질 70의 표준 휘도 양자화 테이블 첫 값(16 * 0.6 = 9.6 → 10)
    assert out.quantization[0][0] == 10


def test_resize50(img):
    data, ext = variants.encode_variant(img, "resize50")
    out = Image.open(io.BytesIO(data))
    assert ext == "png" and out.format == "PNG" and out.size == (576, 448)


def test_screenshot_downscales_long_side(img):
    out = variants.make_variant(img, "screenshot")
    assert out.format == "PNG" and max(out.size) == variants.SCREENSHOT_LONG_SIDE
    assert out.size == (1080, 840)


def test_screenshot_keeps_small_images():
    small = Image.new("RGB", (800, 600), (1, 2, 3))
    assert variants.make_variant(small, "screenshot").size == (800, 600)


def test_pure_and_deterministic(img):
    before = img.tobytes()
    a, _ = variants.encode_variant(img, "jpeg70")
    b, _ = variants.encode_variant(img, "jpeg70")
    assert a == b and img.tobytes() == before


def test_rgba_input_converted():
    out = variants.make_variant(Image.new("RGBA", (10, 10)), "jpeg70")
    assert out.mode == "RGB"


def test_unknown_version():
    with pytest.raises(ValueError):
        variants.encode_variant(Image.new("RGB", (4, 4)), "blur")


def test_no_exif_written(img):
    for v in variants.VERSIONS:
        assert len(variants.make_variant(img, v).getexif()) == 0
