import type { AnalysisOutcome } from './api';
import type { PickedImage } from './types';

// 화면 사이에 넘길 값. 라우트 파라미터(문자열)로 넘기기엔 커서 메모리에만 둔다.
// 이미지(경로)·응답 전체는 디스크에 저장하지 않는다 (개인정보, CLAUDE.md).
// 내 기록에는 판정 값만 따로 저장한다 (historyStore.ts).
let currentImage: PickedImage | null = null;
let lastOutcome: AnalysisOutcome | null = null;
let lastRecordId: string | null = null; // 이 결과를 저장한 기록 ID (내 기록). 저장 내용은 historyStore.ts

export const session = {
  setImage(image: PickedImage) {
    currentImage = image;
    lastOutcome = null;
    lastRecordId = null;
  },
  getImage: () => currentImage,
  /** 검사를 통과한 분석 결과만 저장된다 (api.ts의 parseAnalyzeResponse) */
  setOutcome(outcome: AnalysisOutcome, recordId: string | null = null) {
    lastOutcome = outcome;
    lastRecordId = recordId;
  },
  getOutcome: () => lastOutcome,
  getRecordId: () => lastRecordId,
  clear() {
    currentImage = null;
    lastOutcome = null;
    lastRecordId = null;
  },
};
