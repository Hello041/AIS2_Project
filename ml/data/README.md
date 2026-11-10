# ml/data — 검증 이미지 목록

이미지 파일은 git에 올리지 않는다. git에는 `manifest.csv`, 이 README, 도구 스크립트(`*.py`)만 올린다.

## 폴더

```
ml/data/
├─ incoming/        받은 그대로의 원본 (git 제외). real/, ai/
├─ images/          정식 데이터. manifest에 등록된 파일만 (git 제외). real/, ai/
├─ samples/         측정용 사진 (git 제외, manifest에 넣지 않음)
├─ manifest.csv
├─ build_dataset.py     incoming/ → images/ 변환·복사 + manifest 행 추가
└─ validate_manifest.py
```

## 데이터 구성 (2026-11-04)

원본(`version=original`) 기준 **실제 100 + AI 100**. 주제는 양쪽 모두 풍경·자연.

| | 실제 (`real_0001`~`real_0100`) | AI (`ai_0001`~`ai_0100`) |
|---|---|---|
| 출처 | RAISE 데이터셋, 받은 200장 중 중복 1장 제외 후 무작위 100장 (시드 42) | Cloudflare Workers AI로 직접 생성 (프롬프트 25장면 × 4조건) |
| 생성기 | `camera` | `sdxl` 34, `sdxl-lightning` 33, `flux1-schnell` 33 |
| 수집 (`collected_by`) | 김정효 | 임정민 |
| 라이선스 | `RAISE-research-only` (연구·비상업) | SDXL·SDXL-Lightning `CreativeML-OpenRAIL++-M`, FLUX.1-schnell `Apache-2.0` |
| 해상도 | 약 105만 화소 (원본 약 1,600만 화소에서 축소) | 약 103~105만 화소 (API 출력 그대로) |
| 형식 | PNG 34 / JPEG q75 33 / JPEG q100 33 | PNG 34 (sdxl) / JPEG q75 33 (sdxl-lightning) / JPEG q100 33 (flux1-schnell) |

**실제 사진을 AI 쪽 조건에 맞춘 이유:** 받은 그대로면 실제는 '1,600만 화소 PNG', AI는 '100만 화소, 2/3가 JPEG'라서 모델·스태킹이 AI 흔적 대신 해상도·압축 흔적으로 구분할 수 있다. AI 쪽 JPEG는 API 출력이라 바꿀 수 없으므로 실제 쪽을 맞췄다.
- 면적이 1024×1024가 되도록 Lanczos 축소 (비율 유지)
- 3장씩 돌아가며 PNG / JPEG 품질 75 / JPEG 품질 100, 크로마 4:2:0 (AI 생성기 3종의 출력과 같은 설정·비율)
- 원본 크기 사진은 `incoming/real/`에 남아 있다. 각 행의 `notes`에 RAISE 파일 이름과 변환 내용을 적었다.

남은 차이: 축소 자체가 남기는 흔적(실제 쪽에만 있음), 화면 비율(실제 3:2, AI 9:7·1:1). 비교표 해석 시 한계로 적는다.

## 변형 버전 (B5, 2026-11-10)

원본 200장마다 3개씩 만들어 **총 800행**(실제 400 + AI 400). 같은 `source_id`를 공유하므로 GroupKFold에서 한 원본의 모든 버전이 같은 fold에 들어간다.

| version | 만드는 방법 | 결과 크기 (실제 / AI) |
|---|---|---|
| `jpeg70` | JPEG 품질 70, 4:2:0 재압축 | 원본과 같음 |
| `resize50` | 가로·세로 50% bicubic 축소, PNG | 약 629×417 / 576×448·512×512 |
| `screenshot` | 긴 변 1080px로 bilinear 축소 후 PNG (휴대폰 FHD 화면 캡처 모사). 이미 1080 이하면 크기 그대로 PNG | 1080×716 / 1080×840·**1024×1024** |

- 설정은 `inference/variants.py` 한 곳에만 있다. Sprint 2 판정 안정성(서버)도 같은 함수를 쓴다.
- 주의: FLUX(1024×1024) 33장은 긴 변이 이미 1080 이하라 `screenshot`이 **축소 없이 PNG로 다시 저장만** 된다(픽셀은 원본과 같음). 다른 이미지는 약간 축소된다.

```bash
python ml/data/make_variants.py                  # jpeg70만 (MVP)
python ml/data/make_variants.py --versions all   # 세 가지 전부
```

## build_dataset.py

```bash
python ml/data/build_dataset.py --dry-run
python ml/data/build_dataset.py --collected-by 이름
```

`incoming/`을 읽어 실제 사진은 위 규칙으로 변환하고 AI 이미지는 그대로 복사해 `images/`에 넣고, manifest에 행을 추가한 뒤 `validate_manifest.py`를 실행한다.
이미 manifest에 있는 `image_id`는 건너뛰므로 다시 실행해도 중복되지 않는다. 같은 입력·시드면 같은 결과가 나온다.
AI 생성기는 생성 스크립트의 순환 규칙(`ai_land_NNN`의 번호 `(N-1) % 3` → sdxl, sdxl-lightning, flux1-schnell)으로 정한다.
`incoming/ai/log.jsonl`(생성 스크립트 기록)이 있으면 모델이 순환 규칙과 같은지 확인하고, 시드·프롬프트를 `notes`에 넣는다(FLUX는 시드 지정 불가라 `seed 없음`).

## manifest.csv

- UTF-8(BOM 없음), 쉼표 구분, 첫 줄은 헤더. 값에 쉼표가 있으면 큰따옴표로 감싼다.
- 한 행 = 이미지 파일 하나. 원본 1장에서 버전 4개가 나오면 4행이다.
- 수정 후에는 `python ml/data/validate_manifest.py`로 검사한다.

| 열 | 필수 | 의미 · 허용값 |
|---|---|---|
| `image_id` | O | `{source_id}_{version}`. 전체에서 유일 |
| `source_id` | O | 원본 ID. `real_0001`, `ai_0001`처럼 접두어(`real_`/`ai_`) + 4자리 순번. 같은 원본의 모든 버전이 같은 값을 갖는다. 교차검증(GroupKFold)의 그룹 기준 |
| `label` | O | `real` \| `ai` |
| `version` | O | `original` \| `jpeg70`(JPEG 품질 70 재압축) \| `resize50`(가로·세로 50%) \| `screenshot`(축소 후 PNG) |
| `file_path` | O | `ml/data/` 기준 상대경로. 규칙: `images/{label}/{image_id}.{ext}` |
| `generator` | | 실제 사진은 `camera` 또는 빈칸. AI 이미지는 생성기 이름(소문자·하이픈, 예: `sdxl`, `sdxl-lightning`, `flux1-schnell`, `midjourney-v6`) |
| `source_url` | | 출처 URL. 직접 찍었거나 직접 생성했으면 빈칸 |
| `license` | | 라이선스 (예: `CC0-1.0`, `CC-BY-4.0`, `Unsplash`, `own-photo`, `generator-tos`) |
| `collected_by` | | 수집한 사람 (실명) |
| `notes` | | 자유 기록 |

### 명명 규칙

- `source_id`: `{label}_{4자리 순번}` — 예: `real_0001`, `ai_0042`
- `image_id`: `{source_id}_{version}` — 예: `real_0001_original`, `ai_0042_jpeg70`
- 확장자: `jpeg70` → `.jpg`, `resize50`·`screenshot` → `.png`, `original` → 원본 형식
  (resize50은 축소 효과만 보려고 무손실 PNG로 저장한다 — 압축 효과는 jpeg70이 따로 본다. 2026-11-10 결정)
- 변형 버전 행은 원본 행의 `label`·`generator`·`source_url`·`license`·`collected_by`를 그대로 복사한다.

### 예시

```csv
image_id,source_id,label,version,file_path,generator,source_url,license,collected_by,notes
real_0001_original,real_0001,real,original,images/real/real_0001_original.jpg,camera,https://unsplash.com/photos/XXXX,Unsplash,임정민,
ai_0001_jpeg70,ai_0001,ai,jpeg70,images/ai/ai_0001_jpeg70.jpg,sdxl,,generator-tos,김정효,"직접 생성, JPEG 품질 70 재압축"
```

## validate_manifest.py

```bash
python ml/data/validate_manifest.py            # 기본: ml/data/manifest.csv
python ml/data/validate_manifest.py 경로.csv
```

검사 항목: 헤더 일치, 필수 값, `label`·`version` 허용값, `image_id` 형식·중복, 같은 `source_id` 안의 `label` 혼재, `file_path` 존재.
문제가 없으면 종료 코드 0, 문제 행이 있으면 1, 파일을 읽을 수 없거나 헤더가 다르면 2.
