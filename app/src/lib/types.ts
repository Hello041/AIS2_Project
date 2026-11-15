// 추론 서버 응답 형식 (계획서 §5.4)

export type Band = 'weak' | 'uncertain' | 'strong';

export const BANDS: readonly Band[] = ['weak', 'uncertain', 'strong'];

export type ModelResult = {
  name: string;
  raw_score: number; // 화면에 표시하지 않는다 (§5.4)
  band: Band;
};

/** 모델 주목 영역 (계획서 §12.4). 판정과 무관한 참고 정보. 서버가 만들지 못하면 null */
export type HeatmapPayload = {
  model: string;
  method: string;
  png_base64: string; // 원본 위에 겹친 PNG (긴 변 ≤512px, EXIF 회전 적용됨)
  coverage: number; // 0~1, 원본 면적 중 모델이 실제로 본 비율
  width: number;
  height: number;
};

export type AnalyzeResponse = {
  overall: Band;
  overall_method: 'rule' | 'stacking'; // 화면에 표시하지 않는다 (§5.4)
  models: ModelResult[];
  provenance: unknown | null; // 미구현 시 null
  heatmap?: HeatmapPayload | null; // 선택 필드. 없거나 잘못되면 히트맵 영역만 숨긴다
  elapsed_ms: number;
  disclaimer: string;
};

export type HealthResponse = {
  status: 'ok';
  models: string[];
};

/**
 * 사용자가 고른 이미지(피커가 앱 캐시에 둔 파일). 경로만 들고 있고 앱이 따로 저장하지 않는다.
 * 형식·크기는 피커 값(확장자 기반)을 믿지 않고 업로드 직전에 실제 바이트로 확인한다 (prepare.ts).
 */
export type PickedImage = {
  uri: string;
  /** 피커가 알려 준 해상도. 0이거나 없을 수 있다 (헤더 판정을 못 할 때만 참고) */
  width?: number;
  height?: number;
};
