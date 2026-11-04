# ml/data — 검증 이미지 목록

이미지 파일은 git에 올리지 않는다. git에는 `manifest.csv`, 이 README, 도구 스크립트(`*.py`)만 올린다.

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
| `generator` | | 실제 사진은 `camera` 또는 빈칸. AI 이미지는 생성기 이름(소문자, 예: `sdxl`, `flux1-dev`, `midjourney-v6`, `dalle3`) |
| `source_url` | | 출처 URL. 직접 찍었거나 직접 생성했으면 빈칸 |
| `license` | | 라이선스 (예: `CC0-1.0`, `CC-BY-4.0`, `Unsplash`, `own-photo`, `generator-tos`) |
| `collected_by` | | 수집한 사람 (실명) |
| `notes` | | 자유 기록 |

### 명명 규칙

- `source_id`: `{label}_{4자리 순번}` — 예: `real_0001`, `ai_0042`
- `image_id`: `{source_id}_{version}` — 예: `real_0001_original`, `ai_0042_jpeg70`
- 확장자: `jpeg70` → `.jpg`, `screenshot` → `.png`, `original`·`resize50` → 원본 형식
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
