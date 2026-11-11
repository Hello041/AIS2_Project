# inference — FastAPI 추론 서버

## 설치

Python 3.10 기준. 가상환경을 권장한다.

```bash
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r inference/requirements.txt
pip install -r inference/requirements-dev.txt        # 테스트(pytest)까지
```

테스트: `cd inference && pytest -q` (모델 가중치 없이 돈다).

## 서버 실행

```bash
cd inference
uvicorn main:app --host 0.0.0.0 --port 8000      # 같은 Wi-Fi의 휴대폰에서 접속하려면 반드시 0.0.0.0
DETECTORS=univfd,aide uvicorn main:app --host 0.0.0.0 --port 8000   # 모델 골라서 (PowerShell: $env:DETECTORS="univfd,aide")
```

Windows 방화벽에서 8000 포트 열기 (관리자 PowerShell, 한 번만):
```powershell
New-NetFirewallRule -DisplayName "AIS2 inference 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```
- 노트북 IP 확인: `ipconfig` → Wi-Fi 어댑터의 IPv4 주소. 휴대폰 브라우저에서 `http://<IP>:8000/health`가 열리면 연결 성공.
- 학교 Wi-Fi가 기기 간 통신을 막으면 휴대폰 핫스팟이나 ngrok을 쓴다.

확인용 요청:
```bash
curl http://localhost:8000/health
curl -F "image=@ml/data/images/ai/ai_0001_original.png" http://localhost:8000/analyze
```

서버 동작 메모:
- 업로드는 요청 본문을 직접 스트리밍 파싱해 **메모리(BytesIO)에서만** 다룬다. FastAPI `UploadFile`·`File()`은 1MB 넘는 파일을 임시 파일(디스크)로 넘기므로 쓰지 않는다. 테스트(`test_no_temp_files_used`)가 임시 파일 사용을 막은 채 1MB 넘는 이미지를 보내 확인한다.
- 413: `Content-Length`로 먼저 거르고, 읽는 중에도 10MB(+multipart 여유 64KB)를 넘으면 중단.
- 400: JPEG/PNG/WebP가 아니거나 디코딩 실패, multipart가 아니거나 `image` 필드 없음, **2,500만 화소 초과**(환경 변수 `MAX_IMAGE_PIXELS`로 조정). AIDE 메모리가 해상도에 비례하기 때문(1,600만 화소에서 세 모델 최대 약 10GB).
- 500: 추론 중 예외. 스택트레이스는 서버 로그에만 남고 이미지 정보는 없다.
- 로그: `analyze status=200 bytes=123456 elapsed_ms=17000` 형식. 파일명·EXIF는 남기지 않는다.
- 추론은 한 번에 하나씩(잠금). 동시에 여러 요청이 오면 순서대로 처리한다.

## Detector 추가하기

`detectors/<이름>.py`에 `Detector`(detectors/base.py) 하위 클래스를 **하나** 만들고 `name = "<이름>"`, `_load()`, `_score(img)`를 구현한다.
`score()`는 기반 클래스가 RGB 변환 → `_score` → 0~1 범위 검사 순으로 처리한다. 활성 모델은 환경 변수 `DETECTORS="univfd,bfree"`로 고른다(없으면 univfd, aide, bfree 셋 다).
`main.py`·`banding.py`·`detectors/__init__.py`는 고치지 않는다.

## 가중치·공식 코드 받기

가중치(`weights/`)와 모델 공식 코드(`third_party/`)는 git에 올리지 않는다. 아래 스크립트로 받는다.

```bash
python inference/scripts/download_weights.py              # 사용 중인 모델 전부 (univfd, aide, bfree, 약 4.6GB)
python inference/scripts/download_weights.py --only bfree # 일부만 (univfd,npr,aide,bfree)
python inference/scripts/download_weights.py --list       # 받지 않고 URL·저장 경로만 출력
```

이미 있는 파일은 건너뛰고, 끝나면 파일마다 크기와 sha256을 출력한다.

| 모델 | 저장 경로 | 크기 | 출처 |
|---|---|---|---|
| UnivFD 분류층 | `weights/univfd/fc_weights.pth` | 4KB | UnivFD 저장소 `pretrained_weights/` |
| UnivFD 백본 (CLIP ViT-L/14) | `weights/univfd/ViT-L-14.pt` | 890MB | OpenAI 공식 URL (sha256 `b8cca3fd…a03836`, 스크립트가 검증) |
| NPR (ProGAN 4-class) | `weights/npr/model_epoch_last_3090.pth` | 5.6MB | NPR 저장소 루트 |
| AIDE (SD1.4 학습) | `weights/aide/sd14_train.pth` | 3.35GB | [Google Drive](https://drive.google.com/drive/folders/1qx76UFvDpgCxaPLBCmsA2WY-SSzeJrd4) |
| B-Free (DINOv2 ViT-B/14 reg4) | `weights/bfree/BFREE_dino2reg4/{config.yaml, model_epoch_best.pth}` | 330MB | [GRIP 공식 zip](https://www.grip.unina.it/download/prog/B-Free/weights/BFREE_dino2reg4.zip) (MD5 공식값 일치 확인) |
| 공식 코드 | `third_party/{univfd,npr,aide,bfree}/` | — | 아래 표의 커밋으로 고정 |

**AIDE가 "Too many users have viewed or downloaded this file recently"로 실패하면** Google Drive의 다운로드 한도 때문이다. 몇 시간 뒤 다시 하거나, 구글에 로그인한 브라우저에서 [sd14_train.pth](https://drive.google.com/file/d/1JYD1QO62wHwrvh2MVWS1GPjV314WsHcx/view)를 직접 받아 `inference/weights/aide/sd14_train.pth`에 둔다.

## 라이선스

| | UnivFD | NPR | AIDE |
|---|---|---|---|
| 저장소 (고정 커밋) | [WisconsinAIVision/UniversalFakeDetect](https://github.com/WisconsinAIVision/UniversalFakeDetect) `030495a` | [chuangchuangtan/NPR-DeepfakeDetection](https://github.com/chuangchuangtan/NPR-DeepfakeDetection) `781ced3` | [shilinyan99/AIDE](https://github.com/shilinyan99/AIDE) `6725b71` |
| 코드 라이선스 | MIT (© 2025 WAIV) | **명시 없음** (LICENSE 파일 없음) | MIT (© 2024 Shilin Yan) |
| 가중치 라이선스 | 명시 없음 (분류층은 MIT 저장소에 포함). CLIP 가중치는 OpenAI CLIP 저장소(MIT) 배포 | 명시 없음 | 명시 없음 |
| 가중치 학습 데이터 | ProGAN (CNNDetection 학습셋, 20 클래스) | ProGAN 4 클래스 (car·cat·chair·horse) | SD1.4 (GenImage 하위셋) |
| 요구 패키지 | torch, torchvision (버전 없음). 저장소 안 `models/clip/`의 OpenAI clip 코드 (ftfy, regex, tqdm, pkg_resources) | torch>=1.2.0, torchvision (버전 없음) | 설치 문서: Python 3.10, torch 2.0.1, torchvision 0.15.2. requirements: timm 0.9.6, open-clip-torch 2.24.0, numpy 1.24.3 등 (timm 1.0.12에서도 동일 동작 확인) |

- **NPR은 2026-11-10부터 쓰지 않는다** (B-Free로 교체, 계획서 §7 '11/10 점검 결과'). 다운로드 스크립트에는 비교·재현용으로 남겨 둔다.
- **NPR은 라이선스가 명시되어 있지 않다.** 저작권법상 기본값은 '모든 권리 보유'다. 이 프로젝트에서는 학술·비상업 데모 목적으로만 사용하고, 코드를 저장소에 복사해 커밋하지 않는다(`third_party/`는 git 제외).
- **B-Free** ([grip-unina/B-Free](https://github.com/grip-unina/B-Free) `c6a9f89`, CVPR 2025): GRIP-UNINA 자체 라이선스 — 코드·가중치 모두 **정보·비영리 목적만** 사용·복제·수정 가능, 영리 목적 금지, 저작권 표시 유지, **결과를 공개할 때 원저자 인용 필수**(발표·보고서에 Guillaro et al., CVPR 2025 표기). 학습 데이터: COCO 실제 이미지 + SD2.1 자기조건 재구성·인페인팅. 요구: torch 2.0.1, torchvision 0.15.2, timm>=1.0.12.
- AIDE 저장소의 Chameleon 데이터셋은 "academic research only, commercial use prohibited"이다. 이 프로젝트는 Chameleon을 쓰지 않는다.
- 세 모델 모두 가중치 자체의 라이선스는 명시되어 있지 않다. 서비스 공개(Sprint 2 이후) 전에 다시 확인한다.

## 주의사항

- **UnivFD는 OpenAI `clip` 구현을 쓴다.** 공식 코드는 저장소 안 `models/clip/`(OpenAI CLIP 복사본)으로 `ViT-L/14`를 올린다. CLIP 정규화값은 mean `0.48145466, 0.4578275, 0.40821073`, std `0.26862954, 0.26130258, 0.27577711`. **open_clip으로 바꾸면 가중치와 전처리가 같은지 검증한다.** 이미지 인코더만 올린다(`ml/measure.py`의 `load_univfd`는 `visual.*` 가중치만 골라 인코더만 만든다).
- **UnivFD 전처리: 공식 평가 코드(`validate.py`)대로 Resize 없이 CenterCrop 224** (`detectors/univfd.py` 기본값, 환경 변수 `UNIVFD_PREPROCESS=crop`). 2026-11-10 검증 데이터 200장 비교: crop은 AUC 0.66, CLIP 기본 전처리(Resize 224 → Crop, `UNIVFD_PREPROCESS=resize`)는 AUC 0.45 — 축소하면 흔적이 지워져 모든 이미지를 '실제'(점수 약 0)로 판정한다. crop의 약점: 큰 원본 사진은 가운데 224×224만 보므로 점수가 그 부분 내용에 흔들린다(원본 크기 실제 10장 중 2장 오탐).
- **B-Free 전처리:** ToTensor + ImageNet 정규화만 하고 Resize·Crop은 하지 않는다. 모델 내부에서 504×504 크기 5곳(가운데+네 모서리)을 잘라 평균하고, 504보다 작으면 반복해 채운다. 출력은 로짓 1개(양수 = AI) → sigmoid로 0~1. 공식 데모 4장의 로짓과 소수점 5자리까지 일치 확인(2026-11-10). CPU에서 이미지 크기와 무관하게 약 12초, 상주 0.36GB.
- **AIDE 백본은 따로 받지 않는다.** 모델 생성자가 `resnet_path`·`convnext_path`를 받지만, `sd14_train.pth`에 ConvNeXt-XXL·ResNet 가중치가 모두 들어 있다(8.98억 파라미터). 둘 다 `None`으로 만든 뒤 체크포인트의 `model`을 올리면 키가 모두 일치한다(2026-11-04 확인).
- AIDE 공식 코드의 `data/__init__.py`는 설치하지 않은 `kornia`를 끌어온다. 전처리는 `data/dct.py`만 직접 읽어 쓴다.
- AIDE 출력은 2-클래스 logit이다. Detector에서 AI 쪽 softmax 값을 원점수로 쓴다(0~1, 확률 아님).
- AIDE 저장소의 `requirements.txt`는 `torch==1.11.0`이지만 설치 문서는 torch 2.0.1이다. 이 프로젝트는 설치 문서(2.0.1)를 따른다.
- `numpy`는 1.24.3에 고정한다. torch 2.0.1은 numpy 2.x와 호환되지 않는다.
- `huggingface_hub` 등 간접 의존성은 고정하지 않았다. 설치가 깨지면 동작하는 환경에서 `pip freeze`로 고정한다.
