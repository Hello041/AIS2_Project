"""FastAPI 추론 서버 (계획서 §5.4).

    cd inference && uvicorn main:app --host 0.0.0.0 --port 8000

- GET  /health   → {"status": "ok", "models": [...]}
- POST /analyze  → multipart/form-data, 필드 이름 image

개인정보 (CLAUDE.md):
- 업로드는 **메모리(BytesIO)에서만** 다룬다. FastAPI의 UploadFile·File()은 Starlette가 1MB 넘는 파일을
  SpooledTemporaryFile로 디스크에 넘기므로 쓰지 않고, 요청 본문을 스트리밍으로 직접 파싱한다.
- 로그에는 바이트 크기·처리 시간·상태 코드만 남긴다. 파일명·EXIF·이미지 내용은 남기지 않는다.
- EXIF는 읽지 않는다 (provenance 미구현 → null).

모델은 시작할 때 환경 변수 DETECTORS(없으면 detectors.DEFAULT_DETECTORS)대로 한 번만 로드한다.
판정은 banding.band()·banding.overall()에만 맡긴다 (모델 추가·교체 시 이 파일은 고치지 않는다).
"""
from __future__ import annotations

import io
import logging
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from python_multipart.multipart import MultipartParser, parse_options_header

import banding
from detectors import Detector, create_detectors

log = logging.getLogger("inference")

MAX_IMAGE_BYTES = 10 * 1024 * 1024        # 계획서 §5.4: 10MB 초과 → 413
MULTIPART_OVERHEAD = 64 * 1024            # 경계·헤더 등 multipart 포장 여유분
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
# 디코딩 폭탄·메모리 보호. AIDE는 원본 크기에서 DCT 패치를 뽑아 메모리가 해상도에 비례한다
# (1,600만 화소에서 세 모델 최대 약 10GB, 계획서 §7). 노트북 16GB 기준 2,500만 화소로 제한.
MAX_IMAGE_PIXELS = int(os.environ.get("MAX_IMAGE_PIXELS", 25_000_000))
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS  # 이보다 2배 넘으면 Pillow가 DecompressionBombError
DISCLAIMER = "본 결과는 참고용이며 AI 생성 여부를 보장하지 않습니다."

MSG_400 = "지원하지 않는 이미지입니다"
MSG_413 = "10MB 이하 이미지를 선택해 주세요"
MSG_500 = "분석에 실패했습니다"


class HTTPError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status, self.detail = status, detail


# ---------------------------------------------------------------- multipart (메모리에서만)
class _ImageFieldCollector:
    """multipart 본문에서 name="image" 파트의 바이트만 BytesIO에 모은다. 디스크를 쓰지 않는다."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.image: io.BytesIO | None = None
        self._buf: io.BytesIO | None = None
        self._headers: dict[bytes, bytes] = {}
        self._field = b""
        self._value = b""

    def callbacks(self) -> dict:
        return {
            "on_part_begin": self._part_begin,
            "on_header_field": lambda d, s, e: self._append("_field", d[s:e]),
            "on_header_value": lambda d, s, e: self._append("_value", d[s:e]),
            "on_header_end": self._header_end,
            "on_headers_finished": self._headers_finished,
            "on_part_data": self._part_data,
            "on_part_end": self._part_end,
        }

    def _append(self, attr: str, data: bytes) -> None:
        setattr(self, attr, getattr(self, attr) + data)

    def _part_begin(self) -> None:
        self._headers, self._buf = {}, None

    def _header_end(self) -> None:
        self._headers[self._field.lower()] = self._value
        self._field, self._value = b"", b""

    def _headers_finished(self) -> None:
        _, params = parse_options_header(self._headers.get(b"content-disposition", b""))
        if params.get(b"name") == b"image" and self.image is None:
            self._buf = io.BytesIO()

    def _part_data(self, data: bytes, start: int, end: int) -> None:
        if self._buf is not None:
            self._buf.write(data[start:end])
            if self._buf.tell() > self.limit:
                raise HTTPError(413, MSG_413)

    def _part_end(self) -> None:
        if self._buf is not None:
            self.image, self._buf = self._buf, None


async def read_image_bytes(request: Request) -> bytes:
    ctype, params = parse_options_header(request.headers.get("content-type", ""))
    if ctype != b"multipart/form-data" or b"boundary" not in params:
        raise HTTPError(400, MSG_400)

    body_limit = MAX_IMAGE_BYTES + MULTIPART_OVERHEAD
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > body_limit:
        raise HTTPError(413, MSG_413)  # 본문을 읽기 전에 거른다

    collector = _ImageFieldCollector(MAX_IMAGE_BYTES)
    parser = MultipartParser(params[b"boundary"], collector.callbacks())
    received = 0
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > body_limit:  # Content-Length가 없거나 거짓이어도 막는다
                raise HTTPError(413, MSG_413)
            parser.write(chunk)
        parser.finalize()
    except HTTPError:
        raise
    except Exception:
        raise HTTPError(400, MSG_400) from None  # 깨진 multipart

    if collector.image is None or collector.image.tell() == 0:
        raise HTTPError(400, MSG_400)
    return collector.image.getvalue()


def decode_image(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ALLOWED_FORMATS:
            raise HTTPError(400, MSG_400)
        if img.width * img.height > MAX_IMAGE_PIXELS:
            raise HTTPError(400, MSG_400)
        img.load()
    except HTTPError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError):
        raise HTTPError(400, MSG_400) from None
    return img


# ---------------------------------------------------------------- 앱
def create_app(detectors: list[Detector] | None = None) -> FastAPI:
    """detectors를 주면 그대로 쓰고(테스트), 없으면 시작할 때 DETECTORS로 만들어 로드한다."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        missing = [f for f in ("band", "overall") if not callable(getattr(banding, f, None))]
        if missing:
            raise RuntimeError(f"banding.py에 {missing}가 없습니다 (계획서 B2)")
        dets = detectors if detectors is not None else create_detectors()
        t = time.perf_counter()
        for d in dets:
            d.load()
        log.info("models loaded: %s (%.1fs)", [d.name for d in dets], time.perf_counter() - t)
        app.state.detectors = dets
        app.state.lock = threading.Lock()  # 모델은 동시 추론에 안전하지 않고 메모리도 커서 한 번에 하나씩
        yield

    app = FastAPI(title="AIS2 inference", lifespan=lifespan)
    # 개발용: 모든 출처 허용 (Expo Go·ngrok 시험). 배포 전 출처를 제한할 것.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(HTTPError)
    async def _http_error(_: Request, exc: HTTPError):
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail})

    @app.get("/health")
    async def health(request: Request):
        return {"status": "ok", "models": [d.name for d in request.app.state.detectors]}

    def _analyze_sync(state, img: Image.Image) -> dict:
        with state.lock:
            models = []
            for d in state.detectors:
                score = d.score(img)
                models.append({"name": d.name, "raw_score": score, "band": banding.band(d.name, score)})
        overall, method = banding.overall({m["name"]: m["band"] for m in models})
        return {"overall": overall, "overall_method": method, "models": models}

    @app.post("/analyze")
    async def analyze(request: Request):
        t0 = time.perf_counter()
        size, status = 0, 500
        try:
            data = await read_image_bytes(request)
            size = len(data)
            img = decode_image(data)
            del data
            try:
                result = await run_in_threadpool(_analyze_sync, request.app.state, img)
            except Exception:
                # 스택트레이스는 서버 로그에만. 이미지 정보는 넣지 않는다.
                log.exception("inference failed")
                raise HTTPError(500, MSG_500) from None
            finally:
                img.close()
            status = 200
            return {**result, "provenance": None,
                    "elapsed_ms": round((time.perf_counter() - t0) * 1000), "disclaimer": DISCLAIMER}
        except HTTPError as e:
            status = e.status
            raise
        finally:
            log.info("analyze status=%d bytes=%d elapsed_ms=%d", status, size, (time.perf_counter() - t0) * 1000)

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
