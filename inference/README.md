# inference — FastAPI 추론 서버

## 설치

Python 3.10 기준. 가상환경을 권장한다.

```bash
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r inference/requirements.txt
pip install -r inference/requirements-dev.txt        # 테스트(pytest)까지
```

테스트: `cd inference && pytest -q` (모델 가중치 없이 돈다).

## Detector 추가하기

`detectors/<이름>.py`에 `Detector`(detectors/base.py) 하위 클래스를 **하나** 만들고 `name = "<이름>"`, `_load()`, `_score(img)`를 구현한다.
`score()`는 기반 클래스가 RGB 변환 → `_score` → 0~1 범위 검사 순으로 처리한다. 활성 모델은 환경 변수 `DETECTORS="univfd,npr"`로 고른다(없으면 셋 다).
`main.py`·`banding.py`·`detectors/__init__.py`는 고치지 않는다.

## 가중치·공식 코드 받기

가중치(`weights/`)와 모델 공식 코드(`third_party/`)는 git에 올리지 않는다. 아래 스크립트로 받는다.

```bash
python inference/scripts/download_weights.py              # 전부 (약 4.3GB)
python inference/scripts/download_weights.py --only npr   # 일부만 (univfd,npr,aide)
python inference/scripts/download_weights.py --list       # 받지 않고 URL·저장 경로만 출력
```

이미 있는 파일은 건너뛰고, 끝나면 파일마다 크기와 sha256을 출력한다.

| 모델 | 저장 경로 | 크기 | 출처 |
|---|---|---|---|
| UnivFD 분류층 | `weights/univfd/fc_weights.pth` | 4KB | UnivFD 저장소 `pretrained_weights/` |
| UnivFD 백본 (CLIP ViT-L/14) | `weights/univfd/ViT-L-14.pt` | 890MB | OpenAI 공식 URL (sha256 `b8cca3fd…a03836`, 스크립트가 검증) |
| NPR (ProGAN 4-class) | `weights/npr/model_epoch_last_3090.pth` | 5.6MB | NPR 저장소 루트 |
| AIDE (SD1.4 학습) | `weights/aide/sd14_train.pth` | 3.35GB | [Google Drive](https://drive.google.com/drive/folders/1qx76UFvDpgCxaPLBCmsA2WY-SSzeJrd4) |
| 공식 코드 3종 | `third_party/{univfd,npr,aide}/` | — | 아래 표의 커밋으로 고정 |

**AIDE가 "Too many users have viewed or downloaded this file recently"로 실패하면** Google Drive의 다운로드 한도 때문이다. 몇 시간 뒤 다시 하거나, 구글에 로그인한 브라우저에서 [sd14_train.pth](https://drive.google.com/file/d/1JYD1QO62wHwrvh2MVWS1GPjV314WsHcx/view)를 직접 받아 `inference/weights/aide/sd14_train.pth`에 둔다.

## 라이선스

| | UnivFD | NPR | AIDE |
|---|---|---|---|
| 저장소 (고정 커밋) | [WisconsinAIVision/UniversalFakeDetect](https://github.com/WisconsinAIVision/UniversalFakeDetect) `030495a` | [chuangchuangtan/NPR-DeepfakeDetection](https://github.com/chuangchuangtan/NPR-DeepfakeDetection) `781ced3` | [shilinyan99/AIDE](https://github.com/shilinyan99/AIDE) `6725b71` |
| 코드 라이선스 | MIT (© 2025 WAIV) | **명시 없음** (LICENSE 파일 없음) | MIT (© 2024 Shilin Yan) |
| 가중치 라이선스 | 명시 없음 (분류층은 MIT 저장소에 포함). CLIP 가중치는 OpenAI CLIP 저장소(MIT) 배포 | 명시 없음 | 명시 없음 |
| 가중치 학습 데이터 | ProGAN (CNNDetection 학습셋, 20 클래스) | ProGAN 4 클래스 (car·cat·chair·horse) | SD1.4 (GenImage 하위셋) |
| 요구 패키지 | torch, torchvision (버전 없음). 저장소 안 `models/clip/`의 OpenAI clip 코드 (ftfy, regex, tqdm, pkg_resources) | torch>=1.2.0, torchvision (버전 없음) | 설치 문서: Python 3.10, torch 2.0.1, torchvision 0.15.2. requirements: timm 0.9.6, open-clip-torch 2.24.0, numpy 1.24.3 등 |

- **NPR은 라이선스가 명시되어 있지 않다.** 저작권법상 기본값은 '모든 권리 보유'다. 이 프로젝트에서는 학술·비상업 데모 목적으로만 사용하고, 코드를 저장소에 복사해 커밋하지 않는다(`third_party/`는 git 제외).
- AIDE 저장소의 Chameleon 데이터셋은 "academic research only, commercial use prohibited"이다. 이 프로젝트는 Chameleon을 쓰지 않는다.
- 세 모델 모두 가중치 자체의 라이선스는 명시되어 있지 않다. 서비스 공개(Sprint 2 이후) 전에 다시 확인한다.

## 주의사항

- **UnivFD는 OpenAI `clip` 구현을 쓴다.** 공식 코드는 저장소 안 `models/clip/`(OpenAI CLIP 복사본)으로 `ViT-L/14`를 올린다. CLIP 정규화값은 mean `0.48145466, 0.4578275, 0.40821073`, std `0.26862954, 0.26130258, 0.27577711`. **open_clip으로 바꾸면 가중치와 전처리가 같은지 검증한다.** 이미지 인코더만 올린다(`ml/measure.py`의 `load_univfd`는 `visual.*` 가중치만 골라 인코더만 만든다).
- **UnivFD 전처리 주의:** CLIP 기본 전처리는 Resize 224(bicubic) → CenterCrop 224지만, UnivFD 공식 평가 코드(`validate.py`)는 **Resize 없이 CenterCrop 224만** 한다. 큰 사진에서는 가운데 일부만 보게 된다. 어느 쪽을 쓸지는 `univfd.py` 구현 때 정한다.
- **AIDE 백본은 따로 받지 않는다.** 모델 생성자가 `resnet_path`·`convnext_path`를 받지만, `sd14_train.pth`에 ConvNeXt-XXL·ResNet 가중치가 모두 들어 있다(8.98억 파라미터). 둘 다 `None`으로 만든 뒤 체크포인트의 `model`을 올리면 키가 모두 일치한다(2026-11-04 확인).
- AIDE 공식 코드의 `data/__init__.py`는 설치하지 않은 `kornia`를 끌어온다. 전처리는 `data/dct.py`만 직접 읽어 쓴다.
- AIDE 출력은 2-클래스 logit이다. Detector에서 AI 쪽 softmax 값을 원점수로 쓴다(0~1, 확률 아님).
- AIDE 저장소의 `requirements.txt`는 `torch==1.11.0`이지만 설치 문서는 torch 2.0.1이다. 이 프로젝트는 설치 문서(2.0.1)를 따른다.
- `numpy`는 1.24.3에 고정한다. torch 2.0.1은 numpy 2.x와 호환되지 않는다.
- `huggingface_hub` 등 간접 의존성은 고정하지 않았다. 설치가 깨지면 동작하는 환경에서 `pip freeze`로 고정한다.
