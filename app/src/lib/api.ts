import { File } from 'expo-file-system';

import { API_BASE_URL, USE_MOCK } from './config';
import { MSG_TOO_LARGE, MSG_UNSUPPORTED } from './image';
import { jpegKind } from './imageFormat';
import { MOCK_ANALYZE, MOCK_HEALTH } from './mock';
import { PrepareError, prepareImageForUpload, type PrepareStatus, type PreparedUpload } from './prepare';
import { parseAnalyzeResponse, type PreprocessInfo } from './resultView';
import type { AnalyzeResponse, HealthResponse, PickedImage } from './types';

export type ApiErrorKind =
  | 'not_configured'
  | 'network' // 서버에 닿지 못함
  | 'timeout' // 2분 초과
  | 'bad_image' // 400, 또는 앱에서 형식을 확인할 수 없음
  | 'too_large' // 413
  | 'convert_failed' // 앱에서 JPEG 변환 실패
  | 'resolution_too_high' // 줄여도 화소 제한을 맞추지 못함
  | 'bytes_too_large' // 변환·품질 조정 후에도 10MB 초과
  | 'server' // 500 및 그 밖의 오류 응답, 응답 형식 이상
  | 'aborted'; // 사용자가 화면을 떠나 취소

const MESSAGES: Record<ApiErrorKind, string> = {
  not_configured: '서버 주소(API_BASE_URL)가 설정되지 않았습니다',
  network: '서버에 연결할 수 없습니다',
  timeout: '분석 시간이 2분을 넘어 중단했습니다',
  bad_image: MSG_UNSUPPORTED, // 계획서 §5.4
  too_large: MSG_TOO_LARGE, // 계획서 §5.4
  convert_failed: '이미지 변환에 실패했습니다',
  resolution_too_high: '이미지 해상도가 너무 높아 처리할 수 없습니다',
  bytes_too_large: '이미지 용량이 너무 커서 처리할 수 없습니다',
  server: '분석에 실패했습니다', // 계획서 §5.4
  aborted: '분석을 취소했습니다',
};

const PREPARE_TO_API: Record<PrepareError['kind'], ApiErrorKind> = {
  unsupported: 'bad_image',
  convert_failed: 'convert_failed',
  resolution_too_high: 'resolution_too_high',
  bytes_too_large: 'bytes_too_large',
};

export class ApiError extends Error {
  constructor(public readonly kind: ApiErrorKind) {
    super(MESSAGES[kind]);
    this.name = 'ApiError';
  }

  /** 같은 이미지로 다시 시도하면 결과가 달라질 수 있는 오류인지 */
  get retryable(): boolean {
    return this.kind === 'network' || this.kind === 'timeout' || this.kind === 'server';
  }
}

async function request(path: string, init: RequestInit, signal: AbortSignal): Promise<Response> {
  if (!API_BASE_URL) throw new ApiError('not_configured');
  try {
    return await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal,
      headers: {
        Accept: 'application/json',
        // ngrok 무료 URL의 경고 페이지 회피. 같은 Wi-Fi 직접 연결에는 영향 없음 (CLAUDE.md)
        'ngrok-skip-browser-warning': 'true',
        ...(init.headers ?? {}),
      },
    });
  } catch {
    // 취소·타임아웃 여부는 호출한 쪽이 signal.reason으로 구분한다
    if (signal.aborted) throw new ApiError('aborted');
    throw new ApiError('network');
  }
}

function abortableDelay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new ApiError('aborted'));
    const t = setTimeout(resolve, ms);
    signal.addEventListener('abort', () => {
      clearTimeout(t);
      reject(new ApiError('aborted'));
    });
  });
}

export async function checkHealth(signal: AbortSignal): Promise<HealthResponse> {
  if (USE_MOCK) {
    await abortableDelay(300, signal);
    return MOCK_HEALTH;
  }
  const res = await request('/health', { method: 'GET' }, signal);
  if (!res.ok) throw new ApiError('network');
  const body = (await res.json().catch(() => null)) as Partial<HealthResponse> | null;
  if (body?.status !== 'ok' || !Array.isArray(body.models)) throw new ApiError('network');
  return { status: 'ok', models: body.models.map(String) };
}

/** 분석 한 번의 결과: 서버 응답 + 결과 화면에 필요한 맥락(같은 분석의 /health 모델 목록, 실제 전처리 내역) */
export type AnalysisOutcome = {
  result: AnalyzeResponse;
  expectedModels: string[];
  preprocess: PreprocessInfo;
};

/** 분석 진행 단계 (계획서 §2: 서버 연결 → 이미지 확인 → AI 모델 분석 → 결과 생성) */
export const ANALYSIS_STEPS = ['서버 연결', '이미지 확인', 'AI 모델 분석', '결과 생성'] as const;

/** '이미지 확인' 단계의 세부 안내 */
export const PREPARE_STATUS_TEXT: Record<PrepareStatus, string> = {
  checking: '이미지 형식을 확인하고 있습니다',
  converting: '업로드에 적합한 이미지로 변환하고 있습니다',
};

/**
 * multipart 파트. SDK 58의 전역 fetch(expo/fetch)는 React Native 방식의 { uri, name, type }을 지원하지 않고,
 * bytes()가 있는 객체에서 name·type을 읽어 파트 헤더를 만든다. 파일명·MIME을 실제 데이터 형식에 맞추기 위해
 * expo-file-system File을 그대로 넣지 않고 감싼다 (File의 name·type은 경로 확장자를 따른다).
 */
function uploadPart(upload: PreparedUpload): Blob {
  const file = new File(upload.uri);
  if (!file.exists) throw new ApiError('bad_image');
  return { name: upload.name, type: upload.mimeType, bytes: () => file.bytes() } as unknown as Blob;
}

/**
 * 이미지 한 장을 분석한다. onStep(i)로 지금 진행 중인 단계를 알린다.
 * 서버는 진행률을 보내지 않으므로 단계는 앱이 실제로 하고 있는 일 기준이다:
 * 0 /health 확인 → 1 실제 형식 확인·필요 시 변환 → 2 /analyze 응답 대기 → 3 응답 검사.
 */
export async function analyzeImage(
  image: PickedImage,
  signal: AbortSignal,
  onStep: (step: number) => void,
  onDetail?: (text: string | null) => void,
): Promise<AnalysisOutcome> {
  onStep(0);
  const health = await checkHealth(signal);

  onStep(1);
  let upload: PreparedUpload;
  try {
    upload = await prepareImageForUpload(image, (s) => onDetail?.(PREPARE_STATUS_TEXT[s]));
  } catch (e) {
    if (e instanceof PrepareError) throw new ApiError(PREPARE_TO_API[e.kind]);
    throw new ApiError('convert_failed');
  } finally {
    onDetail?.(null);
  }

  try {
    if (signal.aborted) throw new ApiError('aborted');
    if (__DEV__) {
      // 개발 중 확인용. 파일명·경로 등 이미지 정보는 남기지 않는다.
      console.log('[upload]', {
        source: upload.source.format,
        jpeg: upload.source.format === 'jpeg' ? jpegKind(upload.source) : undefined,
        converted: upload.converted,
        resized: upload.resized,
        mime: upload.mimeType,
        bytes: upload.size,
        size: upload.width && upload.height ? `${upload.width}x${upload.height}` : undefined,
      });
    }

    const preprocess: PreprocessInfo = {
      converted: upload.converted,
      resized: upload.resized,
      reasons: upload.reasons,
    };

    if (USE_MOCK) {
      onStep(2);
      await abortableDelay(1500, signal);
      onStep(3);
      await abortableDelay(300, signal);
      return { result: MOCK_ANALYZE, expectedModels: health.models, preprocess };
    }

    const form = new FormData();
    form.append('image', uploadPart(upload));

    onStep(2);
    const res = await request('/analyze', { method: 'POST', body: form }, signal);

    onStep(3);
    if (res.status === 400) throw new ApiError('bad_image');
    if (res.status === 413) throw new ApiError('too_large');
    if (!res.ok) throw new ApiError('server');
    const body: unknown = await res.json().catch(() => null);
    const result = parseAnalyzeResponse(body); // 규격과 다르면 정상 결과처럼 보여 주지 않는다
    if (!result) throw new ApiError('server');
    return { result, expectedModels: health.models, preprocess };
  } finally {
    upload.cleanup(); // 변환본(임시 JPEG)만 지운다. 원본은 그대로
  }
}
