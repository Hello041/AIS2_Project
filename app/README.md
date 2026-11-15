# app — AI 이미지 판별 (Expo)

휴대폰 Expo Go에서 이미지 한 장을 골라 추론 서버(`inference/`)로 보내고, 결과를 '약함 / 어려움 / 강함' 구간으로 보여 준다. 설계는 계획서 §5.4(API)·§6(앱)을 따른다.

- Expo SDK 58, Expo Router, TypeScript
- **안드로이드 에뮬레이터는 쓰지 않는다.** 실제 휴대폰의 Expo Go(SDK 58 지원 버전)로 개발한다.

## 실행

```bash
cd app
npm install                # 최초 1회
# app/.env 파일을 만들고 서버 주소를 적는다 (git에 올라가지 않음)
#   API_BASE_URL=http://192.168.0.10:8000      # 같은 Wi-Fi: 노트북 IP
#   API_BASE_URL=https://xxxx.ngrok-free.app   # ngrok
#   API_BASE_URL=mock                          # 서버 없이 §5.4 예시 응답으로 화면 확인
npx expo start             # QR 코드를 휴대폰 Expo Go로 스캔
```

- `API_BASE_URL`을 바꾸면 `npx expo start`를 다시 실행한다.
- 서버는 `cd inference && uvicorn main:app --host 0.0.0.0 --port 8000`로 띄운다 (반드시 `0.0.0.0`, Windows 방화벽 8000 포트 허용).
- 노트북 IP는 `ipconfig`의 IPv4 주소. 휴대폰 브라우저에서 `http://<IP>:8000/health`가 열리는지 먼저 확인하면 원인 찾기가 쉽다.
- 휴대폰과 노트북이 통신하지 못하는 Wi-Fi(학교 등)에서는 ngrok이나 휴대폰 핫스팟을 쓴다. 앱은 모든 요청에 `ngrok-skip-browser-warning: true` 헤더를 붙인다.

## 검사

```bash
npx tsc --noEmit
npx expo-doctor
```

## 구조

```
app.config.ts             앱 설정. extra.apiBaseUrl ← API_BASE_URL
assets/fonts/             Pretendard 4종 (v1.3.9 공식 배포, SIL OFL — Pretendard-LICENSE.txt)
src/app/_layout.tsx       루트 스택: (tabs) 위에 analyze·result·record/[id]. 글꼴을 읽을 때까지 스플래시 유지
src/app/(tabs)/           하단 탭: index(홈) · history(내 기록) · settings(설정)
src/app/analyze.tsx       분석 중: 4단계 표시, 120초 타임아웃, 실패·재시도. 성공하면 내 기록에 저장
src/app/result.tsx        결과: 종합 배지, 모델별 3칸 막대, 모델 주목 영역(B-Free), 분석한 이미지, 출처 확인, 안내
src/app/record/[id].tsx   기록 상세: 저장된 판정만 다시 표시 (이미지·히트맵 없음)
src/components/theme.ts   디자인 토큰: 색(네이비·인디고·화이트), Pretendard 글자 크기, 여백·모서리·그림자
src/components/ui.tsx     공통 UI: 로고, 배지, 종합 판정 카드, 모델별 막대, 목록 행, 빈 화면 등
src/components/brand.ts   브랜드 이미지 경로 / BrandSplash.tsx 앱 안 시작 화면·캐릭터
src/lib/api.ts            /health, /analyze 호출, 오류 분류
src/lib/image.ts          이미지 선택 (형식 검사는 하지 않음)
src/lib/imageFormat.ts    실제 형식 판정(파일 시그니처·헤더)과 업로드 계획 — 순수 함수
src/lib/prepare.ts        업로드 전처리: 원본 유지 또는 조건부 JPEG 변환 (expo-image-manipulator)
src/lib/resultView.ts     응답 검사(parseAnalyzeResponse)와 결과 화면 데이터 — 순수 함수
src/lib/history.ts        내 기록 형식·검사·정렬 — 순수 함수
src/lib/historyStore.ts   내 기록 저장소 (expo-file-system, 문서 폴더의 JSON 파일 하나)
src/lib/mock.ts           §5.4 예시 응답 (API_BASE_URL=mock)
```

## 내 기록 (이 기기에만 저장)

- 분석이 성공하면 `analyze.tsx`가 기록을 만들어 저장한다. 저장에 실패해도 결과 화면은 그대로 보인다.
- 파일: 앱 문서 폴더의 `analysis-history.json` (최신 200개). 앱을 다시 실행해도 남고, 앱을 삭제하면 지워진다. 서버로 보내거나 동기화하지 않는다.
- **저장하는 것**: 기록 ID, 분석 시각, 종합 판정, 모델별 판정 구간(이름·band), 분석되지 않은 모델 이름,
  자동 제목(`11월 14일 분석 #2`, 저장할 때 만들어 고정), 사용자가 입력한 제목(40자)·메모(500자, 선택).
  ```json
  {"v":1,"records":[{"id":"mwekoctc-i0000000","analyzedAt":"2026-11-13T06:05:00.000Z","overall":"uncertain",
    "models":[{"name":"univfd","band":"weak"},{"name":"aide","band":"strong"},{"name":"bfree","band":"strong"}],"missing":[]}]}
  ```
- **저장하지 않는 것**: 이미지·썸네일·파일 경로, 히트맵 PNG, EXIF·GPS, 파일명, `raw_score` 등 응답의 나머지 값. `history.ts`의 `toRecord()`가 필요한 필드만 골라 만들고, 읽을 때(`parseRecord`)도 모르는 필드는 버린다.
- 기록 상세는 저장된 판정을 그대로 보여 준다(현재 모델로 다시 계산하지 않음). 고칠 수 있는 것은 제목·메모뿐이다(상세 화면 '편집', 결과 화면 '제목·메모 추가'). 제목을 비우면 자동 제목으로 돌아간다.
- 제목·메모가 없는 이전 기록도 그대로 읽는다(날짜로 만든 제목 표시).
- 삭제: 내 기록에서 길게 누르기 또는 기록 상세의 '이 기록 삭제'(개별), 내 기록·설정의 '전체 삭제'(확인 팝업).

## 이미지 호환성 (업로드 전처리)

피커의 `mimeType`·확장자는 실제 데이터와 다를 수 있어(예: iOS에서 HEIC 데이터가 `.jpg`로 저장되는 경로) 믿지 않는다. 분석 화면의 '이미지 확인' 단계에서 파일을 **읽기 전용으로 열어 헤더만** 읽고(전체를 메모리에 올리지 않음) 실제 형식·해상도를 판정한다.

| 실제 데이터 | 처리 |
|---|---|
| JPEG(보조 이미지 없음)·PNG·WebP, 2,500만 화소·10MB 이하 | **원본 바이트 그대로** 업로드 |
| HEIC/HEIF, AVIF, GIF, BMP, TIFF | 기기 디코더로 열어 JPEG로 변환 |
| **Ultra HDR JPEG**: 유효한 MPF 이미지 2장 이상 + 주 이미지 APP1에 ` hdrgm:Version="` | **원본 그대로** (서버 Pillow 10.4가 MPO가 아닌 JPEG로 받음) |
| 일반 MPO: 유효한 MPF 이미지 2장 이상, 위 표시 없음 | 주 이미지만 JPEG로 변환 (서버 Pillow가 MPO를 거부) |
| MPF 색인을 끝까지 검증할 수 없는 JPEG | 보수적으로 JPEG 변환 (서버가 원본을 받을지 400을 낼지 확신할 수 없음) |
| 2,500만 화소 초과 | 비율 유지, 2,500만 화소 바로 아래까지만 축소해 JPEG로 저장 (디코딩 단계에서 축소 → 원본 크기 비트맵을 만들지 않음) |
| 10MB 초과 | JPEG 품질 0.95 → 0.9 → 0.85 순으로 저장해 10MB 이하가 되는 첫 값 사용 |
| 형식을 알 수 없음, 헤더가 잘린 파일 | 업로드하지 않고 "지원하지 않는 이미지입니다" |
| 변환 실패, 결과가 JPEG가 아님 | 업로드하지 않고 "이미지 변환에 실패했습니다" |
| 줄여도 화소 제한 초과 / 품질을 낮춰도 10MB 초과 | "이미지 해상도가 너무 높아…" / "이미지 용량이 너무 커서…" |

- Ultra HDR 판정은 서버 Pillow 10.4.0 `JpegImagePlugin.jpeg_factory`/`_getmp`의 규칙을 그대로 옮긴 것이다(`imageFormat.ts`의 `jpegKind`). **서버 Pillow 버전이 바뀌면 다시 확인**해야 한다. 변환 결과 검사도 같은 규칙(`serverOpensAsJpeg`)을 쓴다.
- 변환본은 앱 캐시에 **새 파일**(`.jpg`, `image/jpeg`)로 만들고 업로드가 끝나면 지운다. 피커가 준 파일은 읽기만 한다.
- 업로드 파트의 파일명은 `image.jpg`/`image.png`/`image.webp`로, MIME과 함께 **실제 데이터 형식**에 맞춘다(원본 파일명은 보내지 않음).
- **변환하면 잃는 것**: HDR 게인맵과 MPO 보조 이미지, EXIF 전체(GPS 포함), C2PA 출처 서명. 재압축·축소 때문에 AI 탐지 점수가 원본과 달라질 수 있다. 그래서 필요할 때만 변환한다.
- **방향**: 변환본은 디코더가 EXIF Orientation을 픽셀에 반영한 뒤 저장한다(회전 정보 없이 바로 선 이미지). 원본을 그대로 보낼 때는 EXIF가 그대로 서버에 간다(서버가 회전을 반영하는지는 서버 쪽 동작).
- iOS 피커는 `preferredAssetRepresentationMode: Current`(원본 그대로)를 쓴다. `Compatible`이면 iOS가 한 번 재인코딩하고 앱이 다시 인코딩할 수 있어 손실이 두 번 생긴다.

## 브랜드 에셋 (assets/brand)

AI 탐정 로봇 캐릭터 (이름은 미정). 원본 SVG와 생성 스크립트는 `assets/brand/src`.

| 파일 | 용도 |
|---|---|
| `icon.png` (1024, 투명 없음) | 앱 아이콘 (`app.config.ts` `icon`) |
| `android-foreground.png` / `-background.png` / `-monochrome.png` | Android 적응형 아이콘 (전경은 안전 영역 66% 안) |
| `splash-fullbody.png` | 시작 화면 전신 로봇 (네이티브 스플래시 네이비 `#202544`, `imageWidth` 240 + 앱 안 시작 화면) |
| `fullbody-light.png` / `fullbody-dark.png` (@2x·@3x, 기준 160pt) | 전신 캐릭터 — 재사용용 |
| `splash-character.png` | 이전 시작 화면(얼굴 심볼). 지금은 쓰지 않음 |
| `mark.png` (@2x·@3x) | 헤더 로고 (아이콘과 같은 모양) |
| `character-light.png` / `character-dark.png` (@2x·@3x, 기준 120pt) | 밝은/어두운 배경용 캐릭터 — 빈 화면·로딩·오류에서 재사용 (`BrandCharacter`) |

다시 만들기: `python src/make_svg.py <폴더>` → `src/render.sh`(Edge headless로 2048px 렌더) → `python src/compose.py <렌더> <출력> <미리보기>`.

**시작 화면**: 설치 앱은 네이티브 스플래시(네이비 + 로봇)가 Pretendard를 읽는 동안 보이고, 이어서 앱 안 `BrandSplash`가 같은 위치의 전신 로봇 아래에 서비스명·문구를 약 4초 보여 준 뒤 사라진다. 앱 아이콘은 얼굴 심볼(`icon.png`) 그대로다. **Expo Go에서는 네이티브 스플래시 설정이 적용되지 않고**(Expo Go 자체 화면) `BrandSplash`만 보인다. 앱 아이콘도 설치 빌드에서만 바뀐다.

## 향후 과제 (구현하지 않음)

- **점수에 영향을 준 영역 시각화**: 지금의 히트맵은 B-Free의 Attention Rollout(모델이 주목한 분포)이며 AI 생성 흔적의 위치를 검출하지 않는다. 판별 점수에 실제로 영향을 주는 영역(예: 영역을 가렸을 때 점수 변화)을 보여 주는 기능은 방법 선택과 검증이 필요한 연구 과제로 남긴다. 그 전까지 히트맵을 그런 기능처럼 표현하지 않는다.

## 구현 메모

- **업로드**: SDK 58에서는 전역 `fetch`가 `expo/fetch`로 바뀌어 React Native 방식의 `{ uri, name, type }` 파트를 지원하지 않는다. `bytes()`·`name`·`type`을 가진 객체를 `FormData`에 넣는다 (`src/lib/api.ts`).
- **개인정보**: 고른 이미지·응답 전체는 메모리(`src/lib/session.ts`)에만 둔다. 디스크에는 내 기록(판정 값만)만 쓴다. 개발 모드 콘솔에는 형식·변환 여부·크기만 찍고 파일명·경로는 찍지 않는다.
- 화면에 `raw_score`·`overall_method`를 표시하지 않는다 (§5.4).
- **글꼴**: 굵기마다 Pretendard 파일이 달라 `fontWeight` 대신 `theme.ts`의 `font.*`(fontFamily)를 쓴다. Android에서 합성 굵기가 생기지 않게 하기 위해서다.
- **탭 아이콘**: Expo Router `NativeTabs`의 `sf`(iOS SF Symbols)·`md`(Android Material Symbols). 새 아이콘 패키지 없음.
