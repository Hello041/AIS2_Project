import Constants from 'expo-constants';

/** app.config.ts의 extra.apiBaseUrl (= API_BASE_URL). 끝의 '/'는 뗀다. */
export const API_BASE_URL: string = String(Constants.expoConfig?.extra?.apiBaseUrl ?? '')
  .trim()
  .replace(/\/+$/, '');

/** API_BASE_URL=mock 이면 서버 없이 §5.4 예시 응답을 쓴다 (계획서 §6 구현 메모). */
export const USE_MOCK = API_BASE_URL.toLowerCase() === 'mock';

export const ANALYZE_TIMEOUT_MS = 120_000; // 계획서 §2, §6: 2분
export const HEALTH_TIMEOUT_MS = 10_000; // 홈 화면 연결 확인용
// 업로드 크기·화소 제한은 src/lib/imageFormat.ts (SERVER_MAX_BYTES, SERVER_MAX_PIXELS)
