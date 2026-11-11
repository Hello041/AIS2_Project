"""main.py API 테스트 — DummyDetector로 모델 없이 돈다.

banding.py(B2)가 아직 없어도 돌 수 있게 main.banding을 가짜로 바꿔 끼운다.
가짜 규칙: score > 0.7 strong, < 0.3 weak, 나머지 uncertain / 종합은 모두 같으면 그 값, 아니면 uncertain.
"""
import io
import logging
import tempfile
import types

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main
from detectors.dummy import DummyDetector


def _band(name, score):
    return "strong" if score > 0.7 else "weak" if score < 0.3 else "uncertain"


def _overall(bands):
    vals = set(bands.values())
    return (vals.pop() if len(vals) == 1 else "uncertain"), "rule"


@pytest.fixture(autouse=True)
def fake_banding(monkeypatch):
    monkeypatch.setattr(main, "banding", types.SimpleNamespace(band=_band, overall=_overall))


def make_client(*scores):
    dets = [DummyDetector(n, s) for n, s in zip(("univfd", "aide", "bfree"), scores)]
    return TestClient(main.create_app(dets))


def image_bytes(fmt="PNG", size=(64, 48), noise=False):
    if noise:
        arr = np.random.default_rng(0).integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
        img = Image.fromarray(arr)
    else:
        img = Image.new("RGB", size, (10, 120, 200))
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def post(client, data, name="image", filename="secret_name.png", ctype="image/png"):
    return client.post("/analyze", files={name: (filename, data, ctype)})


# ---------------------------------------------------------------- 정상
def test_health():
    with make_client(0.1, 0.5) as c:
        r = c.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "models": ["univfd", "aide"]}


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_analyze_ok_formats(fmt):
    with make_client(0.9, 0.8, 0.95) as c:
        r = post(c, image_bytes(fmt))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"overall", "overall_method", "models", "provenance", "elapsed_ms", "disclaimer"}
    assert body["overall"] == "strong" and body["overall_method"] == "rule"
    assert [m["name"] for m in body["models"]] == ["univfd", "aide", "bfree"]
    assert body["models"][0] == {"name": "univfd", "raw_score": 0.9, "band": "strong"}
    assert body["provenance"] is None and isinstance(body["elapsed_ms"], int)
    assert body["disclaimer"] == main.DISCLAIMER


def test_mixed_bands_go_uncertain():
    with make_client(0.9, 0.1) as c:
        assert post(c, image_bytes()).json()["overall"] == "uncertain"


# ---------------------------------------------------------------- 400
@pytest.mark.parametrize("data", [
    image_bytes("GIF"),                 # 허용 안 되는 형식
    image_bytes("BMP"),
    b"not an image at all",             # 디코딩 실패
    image_bytes("PNG")[:40],            # 잘린 파일
    b"",                                # 빈 파일
])
def test_400_bad_image(data):
    with make_client(0.5) as c:
        r = post(c, data)
    assert r.status_code == 400 and r.json() == {"detail": main.MSG_400}


def test_400_missing_image_field():
    with make_client(0.5) as c:
        assert post(c, image_bytes(), name="photo").status_code == 400


def test_400_not_multipart():
    with make_client(0.5) as c:
        r = c.post("/analyze", content=image_bytes(), headers={"content-type": "image/png"})
    assert r.status_code == 400


def test_400_too_many_pixels(monkeypatch):
    monkeypatch.setattr(main, "MAX_IMAGE_PIXELS", 1000)
    with make_client(0.5) as c:
        assert post(c, image_bytes(size=(64, 48))).status_code == 400


# ---------------------------------------------------------------- 413
def test_413_image_over_10mb():
    data = b"\x89PNG" + b"0" * main.MAX_IMAGE_BYTES  # 10MB + 4바이트
    with make_client(0.5) as c:
        r = post(c, data)
    assert r.status_code == 413 and r.json() == {"detail": main.MSG_413}


def test_413_by_content_length_header():
    with make_client(0.5) as c:
        r = c.post("/analyze", content=b"x", headers={
            "content-type": "multipart/form-data; boundary=abc",
            "content-length": str(main.MAX_IMAGE_BYTES * 2)})
    assert r.status_code == 413


def test_just_under_limit_is_not_413():
    # 10MB 이하면 크기로는 거부하지 않는다 (내용이 이미지가 아니라 400)
    with make_client(0.5) as c:
        assert post(c, b"0" * (main.MAX_IMAGE_BYTES - 10)).status_code == 400


# ---------------------------------------------------------------- 500
def test_500_on_inference_error(caplog):
    with make_client(1.5) as c:  # 범위 밖 점수 → ScoreRangeError
        with caplog.at_level(logging.INFO, logger="inference"):
            r = post(c, image_bytes())
    assert r.status_code == 500 and r.json() == {"detail": main.MSG_500}
    assert "inference failed" in caplog.text


# ---------------------------------------------------------------- 개인정보
def test_no_temp_files_used(monkeypatch):
    """업로드 처리 중 임시 파일을 만들면 실패하게 해 두고 큰(1MB 초과) 이미지를 보낸다."""
    def boom(*a, **k):
        raise AssertionError("임시 파일 사용 금지")
    for fn in ("SpooledTemporaryFile", "TemporaryFile", "NamedTemporaryFile", "mkstemp", "mkdtemp"):
        monkeypatch.setattr(tempfile, fn, boom)
    data = image_bytes("PNG", size=(1200, 1000), noise=True)
    assert len(data) > 1024 * 1024
    with make_client(0.2) as c:
        r = post(c, data)
    assert r.status_code == 200, r.text


def test_logs_only_size_and_time(caplog):
    with make_client(0.2) as c:
        with caplog.at_level(logging.INFO, logger="inference"):
            post(c, image_bytes(), filename="my_private_photo.png")
    assert "my_private_photo" not in caplog.text
    line = [r.getMessage() for r in caplog.records if r.getMessage().startswith("analyze")][-1]
    assert line.startswith("analyze status=200 bytes=") and "elapsed_ms=" in line


def test_startup_fails_without_banding(monkeypatch):
    monkeypatch.setattr(main, "banding", types.SimpleNamespace())
    with pytest.raises(RuntimeError, match="banding"):
        with make_client(0.5):
            pass
