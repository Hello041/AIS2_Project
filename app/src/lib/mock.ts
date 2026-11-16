import type { AnalyzeResponse, HealthResponse } from './types';

// 계획서 §5.4 예시 응답 그대로 (API_BASE_URL=mock 일 때만 사용)
export const MOCK_HEALTH: HealthResponse = { status: 'ok', models: ['univfd', 'aide', 'bfree'] };

export const MOCK_ANALYZE: AnalyzeResponse = {
  overall: 'uncertain',
  overall_method: 'stacking',
  models: [
    { name: 'univfd', raw_score: 0.52, band: 'uncertain' },
    { name: 'aide', raw_score: 0.81, band: 'strong' },
    { name: 'bfree', raw_score: 0.12, band: 'weak' },
  ],
  provenance: null,
  elapsed_ms: 8421,
  disclaimer: '본 결과는 참고용이며 AI 생성 여부를 보장하지 않습니다.',
};
