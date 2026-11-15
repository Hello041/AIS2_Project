"""서버(main.py) ↔ 실제 banding.py·thresholds.yaml 연결 테스트. 모델 가중치 없이 DummyDetector로 돈다.

- test_api.py는 main.banding을 가짜로 바꿔 끼우므로, 실제 판정 로직과의 연결은 여기서 확인한다.
- 가짜 모델 이름은 활성 모델(commfor, aide, bfree)을 쓴다. 실제 AI 모델은 로드·추론하지 않는다.
- 경계값이 B6에서 바뀌어도 깨지지 않게, 각 모델의 점수는 실제 thresholds.yaml 값에서 구간별로 계산한다.
- httpx(TestClient) 없이 ASGI 앱을 직접 호출한다.
- main.create_app이 없는 브랜치(서버 통합 전)에서는 모듈 전체를 건너뛴다.
"""
import asyncio
import io
import json

import pytest
from PIL import Image

import banding
from banding import STRONG, UNCERTAIN, WEAK, load_thresholds

main = pytest.importorskip("main")
if not hasattr(main, "create_app"):
    pytest.skip("main.create_app 없음 (서버 코드와 통합 전)", allow_module_level=True)

from detectors import DEFAULT_DETECTORS  # noqa: E402
from detectors.dummy import DummyDetector  # noqa: E402

ACTIVE = ("commfor", "aide", "bfree")
BOUNDARY = b"----ais2-test-boundary"


# ---------------------------------------------------------------- ASGI 직접 호출
def png_bytes(size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


def multipart(data: bytes) -> bytes:
    return (b"--" + BOUNDARY + b"\r\n"
            b'Content-Disposition: form-data; name="image"; filename="x.png"\r\n'
            b"Content-Type: image/png\r\n\r\n" + data + b"\r\n--" + BOUNDARY + b"--\r\n")


async def _request(app, method: str, path: str, body: bytes = b"", headers: dict | None = None):
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
             "headers": hdrs, "server": ("test", 80), "client": ("test", 1)}
    pending = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    status, chunks = None, []

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    return status, json.loads(b"".join(chunks) or b"null")


def call(detectors, *requests):
    """서버 시작(lifespan) → 요청들 → 종료. [(status, json), ...]를 돌려준다."""
    app = main.create_app(detectors)

    async def run():
        async with app.router.lifespan_context(app):
            return [await _request(app, *r) for r in requests]

    return asyncio.run(run())


def analyze_request():
    body = multipart(png_bytes())
    return ("POST", "/analyze", body, {"content-type": f"multipart/form-data; boundary={BOUNDARY.decode()}",
                                       "content-length": str(len(body))})


def score_in(name: str, target: str) -> float:
    """실제 thresholds.yaml 값으로 해당 구간에 들어가는 점수를 만든다."""
    low, high = load_thresholds()[name]
    if target == WEAK:
        if low <= 0.0:
            pytest.skip(f"{name}: low=0이라 weak 점수가 없음")
        return low / 2
    if target == STRONG:
        if high >= 1.0:
            pytest.skip(f"{name}: high=1이라 strong 점수가 없음")
        return (high + 1.0) / 2
    return (low + high) / 2


@pytest.fixture(autouse=True)
def _no_ensemble_file():
    # 스태킹(C3)은 미구현이라 ensemble.yaml이 있으면 판정이 500이 된다. 이 테스트는 단계 0 규칙만 본다.
    assert not banding.ENSEMBLE_PATH.exists(), "inference/ensemble.yaml이 있으면 이 테스트는 단계 0을 확인할 수 없다"


# ---------------------------------------------------------------- 설정 일치
def test_server_default_models_match_thresholds():
    """서버 기본 모델 = 활성 모델 = thresholds.yaml 모델 (NPR 없음)."""
    assert tuple(DEFAULT_DETECTORS) == ACTIVE
    assert set(load_thresholds()) == set(ACTIVE)


def test_health_lists_active_models():
    [(status, body)] = call([DummyDetector(n, 0.5) for n in ACTIVE], ("GET", "/health"))
    assert status == 200 and body == {"status": "ok", "models": list(ACTIVE)}


# ---------------------------------------------------------------- /analyze → 실제 band·overall
@pytest.mark.parametrize("bands, expected", [
    ((STRONG, STRONG, STRONG), STRONG),
    ((WEAK, WEAK, WEAK), WEAK),
    ((STRONG, STRONG, UNCERTAIN), STRONG),       # 일부 uncertain, 과반수 strong
    ((WEAK, UNCERTAIN, WEAK), WEAK),             # 일부 uncertain, 과반수 weak
    ((UNCERTAIN, UNCERTAIN, STRONG), UNCERTAIN),
    ((STRONG, STRONG, WEAK), UNCERTAIN),         # strong·weak 공존 → uncertain
    ((WEAK, STRONG, UNCERTAIN), UNCERTAIN),      # 셋 다 다름
])
def test_analyze_uses_real_banding(bands, expected):
    scores = {n: score_in(n, b) for n, b in zip(ACTIVE, bands)}
    [(status, body)] = call([DummyDetector(n, s) for n, s in scores.items()], analyze_request())
    assert status == 200, body
    assert body["overall"] == expected and body["overall_method"] == "rule"
    assert body["models"] == [{"name": n, "raw_score": scores[n], "band": b} for n, b in zip(ACTIVE, bands)]
    # 서버 결과가 banding을 직접 부른 결과와 같다
    assert (body["overall"], body["overall_method"]) == banding.overall(dict(zip(ACTIVE, bands)))


def test_model_without_threshold_is_not_judged():
    """경계값 없는 모델(예: 제거한 npr)이 활성화되면 판정하지 않는다.
    현재 main.py는 시작 시 경계값을 검사하지 않아 /analyze가 500이 된다. 시작 검사를 추가하면 서버가
    시작되지 않아야 한다 — 둘 다 '잘못된 판정을 내보내지 않음'으로 통과시킨다."""
    dets = [DummyDetector("commfor", 0.5), DummyDetector("aide", 0.5), DummyDetector("npr", 0.5)]
    try:
        [(status, body)] = call(dets, analyze_request())
    except Exception:
        return  # 시작 단계에서 거부
    assert status == 500 and "overall" not in body
