"""출처 확인 — C2PA 서명과 EXIF 요약 (계획서 §12.4·§12.6 provenance).

    provenance(data, img) -> {"c2pa": "valid"|"invalid"|"none", "summary": {...}|None,
                              "exif": {"camera": str|None, "software": str|None}}

- c2pa
  - valid:   매니페스트가 있고 서명·해시 검증 통과 (신뢰 목록에 없는 인증서도 valid로 본다 —
             summary.issuer로 누가 서명했는지 보여준다)
  - invalid: 매니페스트는 있는데 검증 실패 (이미지가 서명 뒤에 바뀜 등)
  - none:    매니페스트 없음, 또는 외부 URL에만 있는 매니페스트(받으러 가지 않는다)
- summary: c2pa가 none이 아니면 {"issuer", "claim_generator", "ai_generated"}.
  ai_generated는 매니페스트의 actions에 AI 생성 digitalSourceType이 적혀 있는지 여부다.
- exif: 카메라(제조사·모델)와 소프트웨어만. **GPS·촬영 시각·일련번호 등 다른 태그는 읽지 않는다** (CLAUDE.md).

개인정보: 바이트는 메모리(BytesIO)에서만 읽는다. 원격 매니페스트·OCSP를 받으러 외부에 접속하지 않는다
(이미지 안의 URL로 요청하면 사용자가 무엇을 분석했는지 외부에 알려질 수 있다).
출처 확인이 실패해도 분석은 계속한다 — 오류는 none으로 돌린다.
"""
from __future__ import annotations

import io
import logging

from PIL import Image

log = logging.getLogger("inference")

# 계획서 §12.6과 같은 값
VALID, INVALID, NONE = "valid", "invalid", "none"

# IPTC digitalSourceType 중 AI 생성을 뜻하는 값 (끝부분으로 비교)
_AI_SOURCE_TYPES = ("/trainedAlgorithmicMedia", "/compositeWithTrainedAlgorithmicMedia", "/algorithmicMedia")

_EXIF_MAKE, _EXIF_MODEL, _EXIF_SOFTWARE = 0x010F, 0x0110, 0x0131
_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

_context = None


def _c2pa_context():
    """원격 매니페스트·OCSP를 받지 않는 설정. 한 번만 만든다."""
    global _context
    if _context is None:
        import c2pa
        settings = c2pa.Settings.from_dict({"verify": {"remote_manifest_fetch": False, "ocsp_fetch": False}})
        _context = c2pa.Context(settings)
    return _context


def _is_ai(manifest: dict) -> bool:
    for assertion in manifest.get("assertions") or []:
        if "actions" not in str(assertion.get("label", "")):
            continue
        for action in (assertion.get("data") or {}).get("actions") or []:
            if str(action.get("digitalSourceType") or "").endswith(_AI_SOURCE_TYPES):
                return True
    return False


def read_c2pa(data: bytes, fmt: str | None = None) -> tuple[str, dict | None]:
    try:
        import c2pa
        reader = c2pa.Reader.try_create(_MIME.get(fmt or "", ""), io.BytesIO(data), context=_c2pa_context())
    except Exception as e:  # 원격 매니페스트(Remote), 깨진 JUMBF 등 → 확인할 수 없음
        log.info("c2pa unreadable: %s", type(e).__name__)
        return NONE, None
    if reader is None:
        return NONE, None
    try:
        state = reader.get_validation_state()
        manifest = reader.get_active_manifest() or {}
    finally:
        reader.close()
    status = VALID if state in ("Valid", "Trusted") else INVALID
    summary = {
        "issuer": (manifest.get("signature_info") or {}).get("issuer"),
        "claim_generator": manifest.get("claim_generator"),
        "ai_generated": _is_ai(manifest),
    }
    return status, summary


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\x00", "").strip()
    return text[:100] or None


def read_exif(img: Image.Image) -> dict:
    try:
        exif = img.getexif()
    except Exception:
        return {"camera": None, "software": None}
    make, model = _clean(exif.get(_EXIF_MAKE)), _clean(exif.get(_EXIF_MODEL))
    if make and model and model.lower().startswith(make.lower()):
        camera = model  # "Canon" + "Canon EOS R5" → "Canon EOS R5"
    else:
        camera = " ".join(p for p in (make, model) if p) or None
    return {"camera": camera, "software": _clean(exif.get(_EXIF_SOFTWARE))}


def provenance(data: bytes, img: Image.Image) -> dict:
    status, summary = read_c2pa(data, img.format)
    return {"c2pa": status, "summary": summary, "exif": read_exif(img)}
