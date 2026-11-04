# CLAUDE.md — AIS2_Project (18조 AI 이미지 판별 서비스)

이 파일은 이 저장소에서 작업하는 Claude Code가 매 세션 읽는 규칙이다. 세부 설계는 `docs/`의 계획서를 따르고, 이 파일과 계획서가 다르면 **계획서가 우선**이다. 계획서에 없는 결정이 필요하면 추측하지 말고 사용자에게 묻는다.

## 프로젝트 한 줄 요약

휴대폰 앱(Expo)에서 이미지 한 장을 고르면 노트북의 FastAPI 추론 서버가 모델 3종(UnivFD, AIDE, NPR)으로 분석하고, 결과를 '약함 / 어려움 / 강함' 세 구간으로 보여준다. AI 생성 여부를 단정하지 않는 **참고용** 서비스다.

- MVP 데모: **2026-11-18** (11/10 점검, 11/14 앙상블 채택 결정)
- 담당: 김정효(모델·추론 서버), 임정민(앱) — 유동적

## 참고 문서 (docs/)

| 문서 | 용도 |
|---|---|
| `18조_MVP_완성본_구현계획서.md` | **구현의 기준.** 섹션 번호(§5.3 등)는 이 문서 기준 |
| `AI_이미지_판별_서비스_기획서.md` | 원 기획. 계획서와 다른 점은 검토 문서 8번 참고 |
| `18조_진행순서_및_검토.md` | 작업 순서(A1~D6)와 알려진 문제·미결 질문 |

## 저장소 구조

```
app/          Expo(React Native) 앱
inference/    FastAPI 추론 서버
  main.py           /health, /analyze
  detectors/        base.py(인터페이스), univfd.py, aide.py, npr.py
  banding.py        원점수→구간, 종합 판정 (판정 로직은 여기에만)
  thresholds.yaml   모델별 원점수 경계값
  ensemble.yaml     fit_ensemble.py가 생성. 손으로 고치지 않음
  weights/          가중치 (git 제외)
  tests/            단위 테스트 (위치는 팀 확정 전 임시)
ml/           measure.py, score_samples.py, fit_ensemble.py, data/manifest.csv
docs/
```

## 반드시 지킬 규칙

### 모델·판정
- 모든 Detector는 `score(img: PIL.Image) -> float`로 **0~1, 클수록 AI 쪽** 원점수를 반환한다. 확률이 아니다. 필요하면 sigmoid로 맞춘다.
- 모델 추가·교체는 `detectors/` 모듈 하나로 끝나야 한다. 이를 위해 `main.py`, `banding.py`를 고치게 된다면 설계가 잘못된 것이다.
- 모델은 서버 시작 시 한 번만 로드한다. 추론은 `torch.inference_mode()`, 배치 1, CPU.
- UnivFD는 CLIP **이미지 인코더만** 올린다. 공식 코드는 OpenAI `clip` 패키지를 쓰므로, open_clip으로 바꾸면 가중치·전처리가 같은지 검증한다.
- 경계값: `score < low` → `weak`, `low ≤ score ≤ high` → `uncertain`, `score > high` → `strong`.
- 종합 판정은 `banding.overall()` 하나에만 둔다. `ensemble.yaml`이 있으면 스태킹, 없으면 규칙(단계 0).
- 단계 0 규칙: ① strong과 weak가 함께 있으면 uncertain ② 아니면 2개 이상 나온 구간 ③ (셋 다 다르면 uncertain — ①에 포함되므로 별도 분기 불필요). 모델 2개일 때는 같으면 그 구간, 다르면 uncertain.
- 판단이 애매하면 항상 `uncertain` 쪽으로 기운다 (FPR 우선).
- 스태킹 학습 시 Platt·LR·τ·t_high는 **각 fold의 학습 부분에서만** 맞춘다. 교차검증은 `GroupKFold`(원본 ID 기준, 5-fold).

### 개인정보
- 업로드 이미지는 `BytesIO`로 메모리에서만 다룬다. 디스크·임시파일·로그에 남기지 않는다.
- 로그에는 크기와 처리 시간만 남긴다. 파일명도 남기지 않는다.
- EXIF를 다룰 때 GPS는 응답·저장 어디에도 넣지 않는다.

### API (계획서 §5.4가 기준)
- `GET /health` → `{"status": "ok", "models": [...]}`
- `POST /analyze` multipart, 필드 `image`. 응답 필드: `overall`, `overall_method`(`rule`|`stacking`), `models[{name, raw_score, band}]`, `provenance`(미구현 시 `null`), `elapsed_ms`, `disclaimer`.
- 오류: 400(형식·디코딩), 413(10MB 초과), 500(추론 오류). **413은 FastAPI가 자동으로 내지 않으므로 직접 검사한다.**
- 앱은 `raw_score`와 `overall_method`를 화면에 표시하지 않는다.

### 앱
- 안드로이드 에뮬레이터를 쓰지 않는다 (서버 노트북 RAM 16GB). 실제 휴대폰 Expo Go로 개발한다.
- 서버 주소는 `API_BASE_URL` 환경 변수. 노트북 IP와 ngrok URL을 바꿔 끼울 수 있어야 한다.
- ngrok 무료 URL에는 요청마다 `ngrok-skip-browser-warning: true` 헤더를 붙인다.
- 타임아웃은 `AbortController` 120초.
- iOS에서 HEIC가 넘어오거나 `fileSize`/`mimeType`이 비어 있을 수 있다. 형식 검사는 이 경우를 처리한다.
- 결과 화면은 숫자 없이 모델별 3칸 막대 + 종합 배지 + 안내 문구.

### 저장소·협업
- 가중치, 이미지, `scores.csv` 등 데이터 파일은 커밋하지 않는다. 가중치 받는 법은 `inference/README.md`에 적는다.
- 기능 브랜치 → PR → 상호 리뷰 → `main`. `main`에 직접 커밋하지 않는다.
- 새 의존성은 `requirements.txt`에 **버전을 고정**해 추가한다 (AIDE가 특정 `timm` 버전을 요구할 수 있음).
- 측정값·결정 사항은 계획서의 해당 섹션(§7 등)에 기록한다.

## 자주 쓰는 명령

```bash
# 추론 서버 (같은 Wi-Fi 시연: 반드시 0.0.0.0, Windows 방화벽 8000 포트 허용)
cd inference && uvicorn main:app --host 0.0.0.0 --port 8000

# 테스트
cd inference && pytest -q

# 측정·채점
python ml/measure.py
python ml/score_samples.py      # → ml/scores.csv
python ml/fit_ensemble.py       # → inference/ensemble.yaml + 비교표

# 앱
cd app && npx expo start
```

## 작업 방식
- 작업을 시작하기 전에 관련 계획서 섹션을 읽고, 변경 범위를 짧게 말한 뒤 진행한다.
- 완료 기준(계획서 표의 '완료 기준' 열)을 실제로 실행해서 확인하고 결과를 보고한다. 확인 못 한 것은 못 했다고 말한다.
- 계획서에 '확인 필요'로 남은 항목(아래)을 건드리게 되면 임의로 정하지 말고 선택지를 제시한다.

## 미결 사항 (팀 결정 전)
- HMAC 서명 대상: 문자열 그대로 전달 vs 실수 자릿수 고정 (JS가 `1.0`→`1`로 바꾸는 문제)
- 전이학습·판정 안정성 표시 방식이 기획서와 다른 것이 의도된 변경인지
- `shared/`를 HF Spaces Docker 빌드에 포함하는 방법
- `banding` 단위 테스트 위치 (임시: `inference/tests/`)
- `usage_daily.day` 기준 시간대
- `manifest.csv`에 파일 경로·생성기 열 추가 여부
