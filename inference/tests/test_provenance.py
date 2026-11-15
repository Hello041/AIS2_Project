"""provenance.py 테스트. C2PA 샘플(ml/data/c2pa_samples, 커밋 제외)이 없으면 그 테스트만 건너뛴다.

샘플 받기 (c2pa-python 저장소의 공개 테스트 이미지, MIT/Apache-2.0):
    https://raw.githubusercontent.com/contentauth/c2pa-python/main/tests/fixtures/{C.jpg,A.jpg,cloud.jpg}
"""
import io
from pathlib import Path

import pytest
from PIL import Image

import provenance as prov

SAMPLES = Path(__file__).resolve().parents[2] / "ml" / "data" / "c2pa_samples"


def jpeg(exif: Image.Exif | None = None) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (50, 100, 150)).save(buf, "JPEG", exif=exif or Image.Exif())
    return buf.getvalue()


def run(data: bytes) -> dict:
    with Image.open(io.BytesIO(data)) as img:
        return prov.provenance(data, img)


def sample(name: str) -> bytes:
    path = SAMPLES / name
    if not path.exists():
        pytest.skip(f"{path} 없음 (파일 머리 주석 참고)")
    return path.read_bytes()


# ---------------------------------------------------------------- 형식
def test_plain_image_has_no_c2pa_and_empty_exif():
    assert run(jpeg()) == {"c2pa": "none", "summary": None, "exif": {"camera": None, "software": None}}


def test_png_and_webp_do_not_fail():
    for fmt in ("PNG", "WEBP"):
        buf = io.BytesIO()
        Image.new("RGB", (40, 40)).save(buf, fmt)
        assert run(buf.getvalue())["c2pa"] == "none"


def test_garbage_bytes_are_none_not_error():
    status, summary = prov.read_c2pa(b"\xff\xd8\xff" + b"\x00" * 100, "JPEG")
    assert (status, summary) == ("none", None)


# ---------------------------------------------------------------- EXIF
def test_exif_camera_and_software_only_no_gps():
    exif = Image.Exif()
    exif[0x010F] = "Canon"
    exif[0x0110] = "Canon EOS R5"
    exif[0x0131] = "Adobe Photoshop 25.0"
    exif[0x8825] = {1: "N", 2: (37.0, 33.0, 0.0)}  # GPS IFD
    out = run(jpeg(exif))
    assert out["exif"] == {"camera": "Canon EOS R5", "software": "Adobe Photoshop 25.0"}
    assert "37" not in repr(out) and "gps" not in repr(out).lower()


def test_exif_make_and_model_are_joined():
    exif = Image.Exif()
    exif[0x010F] = "samsung"
    exif[0x0110] = "SM-S918N\x00"
    assert run(jpeg(exif))["exif"]["camera"] == "samsung SM-S918N"


# ---------------------------------------------------------------- C2PA 샘플
def test_signed_sample_is_valid_and_ai_generated():
    out = run(sample("C.jpg"))
    assert out["c2pa"] == "valid"
    assert out["summary"]["issuer"] == "C2PA Test Signing Cert"
    assert out["summary"]["ai_generated"] is True


def test_tampered_sample_is_invalid():
    data = bytearray(sample("C.jpg"))
    data[-2000] ^= 0xFF  # 서명 뒤에 이미지 데이터를 바꿈
    assert run(bytes(data))["c2pa"] == "invalid"


def test_unsigned_sample_is_none():
    assert run(sample("A.jpg"))["c2pa"] == "none"


def test_remote_manifest_is_not_fetched():
    # 외부 URL에만 매니페스트가 있는 이미지. remote_manifest_fetch=False라 c2pa가
    # "must fetch remote manifests" 오류를 내고(받으러 가지 않음) → none.
    # (c2pa는 네이티브 라이브러리라 Python socket을 막는 방식으로는 검사할 수 없다)
    assert prov.read_c2pa(sample("cloud.jpg"), "JPEG") == ("none", None)
