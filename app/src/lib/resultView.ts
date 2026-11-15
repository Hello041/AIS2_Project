// 결과 화면용 데이터 (순수 함수, Expo 의존성 없음 → Node에서 검증 가능).
//
// 원칙 (계획서 §5.4·§6, 팀 합의):
// - 종합 판정은 서버의 overall, 모델별 판정은 서버의 band를 그대로 쓴다. 앱은 점수·판정을 다시 계산하지 않는다.
// - raw_score·overall_method·elapsed_ms는 화면 데이터에 넣지 않는다.
// - 응답이 규격과 다르면 정상 결과처럼 보여 주지 않는다(null → 오류 화면).

import {
  NOT_ANALYZED_LABEL,
  OVERALL_DESCRIPTION,
  OVERALL_LABEL,
  SEGMENT_LABEL,
  UNCERTAIN_NOTE,
  modelDisplayName,
} from './labels';
import { BANDS, type AnalyzeResponse, type Band } from './types';

/** 서버 응답을 검사한다. 규격(§5.4)에 맞지 않으면 null. */
export function parseAnalyzeResponse(v: unknown): AnalyzeResponse | null {
  if (!v || typeof v !== 'object') return null;
  const r = v as Record<string, unknown>;
  if (!BANDS.includes(r.overall as Band)) return null; // overall 누락·예상 밖 값
  if (!Array.isArray(r.models) || r.models.length === 0) return null; // 분석한 모델이 하나도 없음
  const seen = new Set<string>();
  for (const m of r.models) {
    if (!m || typeof m !== 'object') return null;
    const mm = m as Record<string, unknown>;
    if (typeof mm.name !== 'string' || mm.name.length === 0) return null;
    if (!BANDS.includes(mm.band as Band)) return null;
    if (seen.has(mm.name)) return null; // 같은 모델이 두 번 → 어느 쪽이 맞는지 알 수 없음
    seen.add(mm.name);
  }
  if (typeof r.disclaimer !== 'string') return null;
  return v as AnalyzeResponse;
}

/** 업로드 전처리 결과 (prepare.ts의 PreparedUpload에서 가져온 실제 처리 내역) */
export type PreprocessInfo = {
  converted: boolean;
  resized: boolean;
  reasons: readonly ('format' | 'mpo' | 'pixels' | 'bytes')[];
};

export type ModelRow = {
  key: string;
  name: string;
  /** null = 서버가 분석하겠다고 알린 모델인데 응답에 결과가 없음 */
  band: Band | null;
  bandLabel: string;
};

export type HeatmapView = {
  modelName: string;
  uri: string; // data:image/png;base64,…
  aspect: number; // 가로/세로
  coveragePct: number; // 0~100 정수
  partial: boolean; // 모델이 이미지 일부만 봤는지 (범위 밖 영역 있음)
};

export type ResultView = {
  overall: { band: Band; label: string; description: string; note?: string };
  models: ModelRow[];
  heatmap: HeatmapView | null;
  provenance: { title: string; detail?: string };
  preprocess: { headline: string; details: string[] } | null;
  disclaimer: string;
};

const PNG_BASE64_PREFIX = 'iVBORw0KGgo'; // PNG 시그니처(89 50 4E 47 0D 0A 1A 0A)의 base64

/** 서버의 heatmap 필드를 검사한다. 없거나 형식이 맞지 않으면 null → 히트맵 영역만 숨긴다(판정 화면은 그대로). */
export function heatmapView(v: unknown): HeatmapView | null {
  if (!v || typeof v !== 'object') return null;
  const h = v as Record<string, unknown>;
  const { model, png_base64: b64, coverage, width, height } = h;
  if (typeof model !== 'string' || model.length === 0) return null;
  if (typeof b64 !== 'string' || b64.length < 100 || !b64.startsWith(PNG_BASE64_PREFIX)) return null;
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(b64)) return null;
  if (typeof coverage !== 'number' || !Number.isFinite(coverage) || coverage <= 0 || coverage > 1) return null;
  const okSide = (n: unknown) => typeof n === 'number' && Number.isInteger(n) && n > 0 && n <= 2048;
  if (!okSide(width) || !okSide(height)) return null;
  return {
    modelName: modelDisplayName(model),
    uri: `data:image/png;base64,${b64}`,
    aspect: (width as number) / (height as number),
    coveragePct: Math.max(1, Math.round(coverage * 100)),
    partial: coverage < 0.95,
  };
}

const C2PA_TEXT: Record<string, { title: string; detail?: string }> = {
  valid: { title: 'C2PA 출처 기록이 확인되었습니다.' },
  invalid: { title: 'C2PA 출처 기록이 있으나 검증에 실패했습니다.', detail: '기록이 손상되었거나 변경되었을 수 있습니다.' },
  none: {
    title: 'C2PA 출처 기록이 확인되지 않았습니다.',
    detail: '기록이 없다는 사실만으로 AI 생성 이미지라고 판단할 수 없습니다.',
  },
};

/** provenance가 null이면 '준비 중'. 값이 있으면 c2pa 상태만 보여 준다(EXIF·위치 정보는 표시하지 않음). */
export function provenanceView(p: unknown): { title: string; detail?: string } {
  if (p == null) return { title: '준비 중', detail: 'C2PA 출처 확인은 아직 제공하지 않습니다.' };
  const c2pa = typeof p === 'object' ? (p as Record<string, unknown>).c2pa : undefined;
  if (typeof c2pa === 'string' && C2PA_TEXT[c2pa]) return C2PA_TEXT[c2pa];
  return { title: '출처 정보를 표시할 수 없습니다.' };
}

export function preprocessView(pre: PreprocessInfo | null): ResultView['preprocess'] {
  if (!pre) return null; // 처리 내역을 모르면 아무것도 표시하지 않는다
  if (!pre.converted) return { headline: '원본 이미지를 그대로 분석했습니다.', details: [] };
  const details: string[] = [];
  if (pre.reasons.includes('format')) details.push('서버가 받지 않는 형식(HEIC 등)이라 JPEG로 변환했습니다.');
  if (pre.reasons.includes('mpo')) details.push('보조 이미지가 포함된 사진이라 기본 이미지만 JPEG로 변환했습니다.');
  if (pre.resized) details.push('해상도 제한(2,500만 화소)에 맞춰 크기를 줄였습니다.');
  if (pre.reasons.includes('bytes')) details.push('용량 제한(10MB)에 맞춰 다시 압축했습니다.');
  details.push('변환 과정에서 결과가 원본과 다소 달라질 수 있습니다.');
  return { headline: '이미지 형식 또는 크기 제한에 맞춰 변환된 이미지로 분석했습니다.', details };
}

/** 종합 판정 표시 (결과 화면·기록 상세 공통) */
export function overallView(band: Band): ResultView['overall'] {
  return {
    band,
    label: OVERALL_LABEL[band],
    description: OVERALL_DESCRIPTION[band],
    note: band === 'uncertain' ? UNCERTAIN_NOTE : undefined,
  };
}

/**
 * 모델별 행 (결과 화면·기록 상세 공통).
 * expectedModels: 같은 분석에서 /health가 알려 준 모델 목록. 여기 있는데 결과에 없는 모델만 '분석되지 않음'으로
 * 덧붙인다(없는 모델을 uncertain 등으로 채우지 않는다). 모르면 null → 결과에 있는 모델만 보여 준다.
 */
export function modelRows(
  models: readonly { name: string; band: Band }[],
  expectedModels: readonly string[] | null,
): ModelRow[] {
  const rows: ModelRow[] = models.map((m) => ({
    key: m.name,
    name: modelDisplayName(m.name),
    band: m.band,
    bandLabel: SEGMENT_LABEL[m.band],
  }));
  const present = new Set(models.map((m) => m.name));
  for (const name of expectedModels ?? []) {
    if (!present.has(name)) {
      rows.push({ key: `missing:${name}`, name: modelDisplayName(name), band: null, bandLabel: NOT_ANALYZED_LABEL });
      present.add(name);
    }
  }
  return rows;
}

/** 결과 화면 데이터를 만든다. */
export function buildResultView(
  res: AnalyzeResponse,
  expectedModels: readonly string[] | null,
  pre: PreprocessInfo | null,
): ResultView {
  return {
    overall: overallView(res.overall),
    models: modelRows(res.models, expectedModels),
    heatmap: heatmapView(res.heatmap),
    provenance: provenanceView(res.provenance),
    preprocess: preprocessView(pre),
    disclaimer: res.disclaimer,
  };
}
