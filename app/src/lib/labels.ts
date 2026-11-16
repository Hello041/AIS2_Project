import type { Band } from './types';

/** 종합 판정 이름 (팀 용어표, 2026-11 결과 화면 개선 요청) */
export const OVERALL_LABEL: Record<Band, string> = {
  weak: 'AI 생성 흔적 약함',
  uncertain: '판단하기 어려움',
  strong: 'AI 생성 흔적 강함',
};

export const OVERALL_DESCRIPTION: Record<Band, string> = {
  weak: 'AI 생성 흔적이 약하게 나타났습니다.',
  uncertain: 'AI 생성 여부를 판단하기 어려운 결과입니다.',
  strong: 'AI 생성 흔적이 강하게 나타났습니다.',
};

/** uncertain이 '분석 실패'로 읽히지 않도록 덧붙이는 설명 (판정 로직과 무관한 고정 문구) */
export const UNCERTAIN_NOTE = '분석이 실패한 것이 아니라, 모델들의 결과만으로는 어느 한쪽이라고 보기 어려운 경우입니다.';

export const OVERALL_NOTICE = '본 결과는 AI 생성 흔적을 분석한 참고 정보이며, 이미지의 실제 생성 여부를 확정하지 않습니다.';
export const MODELS_NOTICE = '모델별 결과는 AI 생성 흔적에 대한 추정 구간이며 확률이 아닙니다.';
/** 모델 간 결과가 다를 수 있음을 알리는 고정 문구. 앱은 불일치 여부를 따로 판정하지 않는다. */
export const MODELS_DIFFER_NOTE =
  '모델마다 분석 방식이 달라 결과가 서로 다를 수 있습니다. 위의 종합 판정은 서버가 모델별 결과를 함께 고려해 정한 것입니다.';
export const NOT_ANALYZED_LABEL = '분석되지 않음';

/** 히트맵(모델 주목 영역) 안내 — 'AI 생성 의심 영역'이라고 부르지 않는다 (판정과 무관한 주목 위치) */
export const HEATMAP_NOTICE = '색상은 이미지 내 상대적인 모델 주목 강도를 나타내며, AI 생성의 증거가 아닙니다.';
/**
 * 보조 안내 (접어 둘 수 있음). Attention Rollout은 모델의 주목 분포이며 AI 생성 흔적의 위치를 검출하지 않는다.
 * 빨강을 'AI 의심 영역'·'확률 높음'으로 표현하지 않는다. 색은 이미지마다 정규화한 상대값이다.
 * (점수에 실제로 영향을 준 영역을 보여 주는 기능은 연구·검증이 필요한 향후 과제 — app/README.md)
 */
export const HEATMAP_RELATIVE_NOTE =
  '빨간색은 이 이미지 안에서 모델이 상대적으로 더 주목한 영역을 의미합니다. AI 생성이 의심되는 영역을 직접 나타내는 것은 아닙니다. 색상은 이미지마다 개별적으로 정규화되므로 이미지 간 비교에 사용할 수 없습니다.';
/** 범례 설명: 한 줄에 하나씩 (색만 보고 판정 색과 헷갈리지 않도록) */
export const HEATMAP_LEGEND_ITEMS = [
  { key: 'blue', label: '파랑', text: '상대적으로 낮은 주목' },
  { key: 'yellow', label: '노랑', text: '중간 정도의 주목' },
  { key: 'red', label: '빨강', text: '상대적으로 높은 주목' },
  { key: 'hatch', label: '회색 빗금', text: 'B-Free가 분석하지 않은 영역' },
] as const;
export function heatmapCoverageNote(modelName: string, pct: number, partial: boolean): string {
  return partial
    ? `${modelName}는 이 이미지의 약 ${pct}%만 분석했습니다. 회색 빗금은 모델이 보지 않은 영역이며 AI 생성 여부와 관계없습니다.`
    : `${modelName}가 분석한 영역에 주목 정도를 색으로 겹쳐 표시했습니다.`;
}

/** 하단 참고 사항 (접어 둘 수 있는 상세 내용) */
export const GUIDE_ITEMS = [
  'AI 탐지 모델의 결과는 참고 정보입니다.',
  '실제 사진도 AI 생성 이미지로 잘못 판단될 수 있습니다.',
  '이미지 압축, 크기 변경, 스크린샷 등으로 결과가 달라질 수 있습니다.',
  'AI 생성 여부를 확정적으로 보장하지 않습니다.',
];

/** 모델별 3칸 막대의 칸 이름 (계획서 §6) */
export const SEGMENT_LABEL: Record<Band, string> = {
  weak: '약함',
  uncertain: '어려움',
  strong: '강함',
};

/**
 * 판정 구간 색 (2026-11 디자인 팔레트). dot = 팔레트 원색(막대 테두리·점), fg = 흰 배경에서 읽히는 진한 글자색, bg = 옅은 배경.
 * 히트맵의 파랑→노랑→빨강(모델 주목 강도)과는 의미가 다르다. 판정 색은 항상 글자(약함/어려움/강함)와 함께 쓴다.
 */
export const BAND_COLOR: Record<Band, { bg: string; fg: string; dot: string }> = {
  weak: { bg: '#EAF1FB', fg: '#2D62AE', dot: '#4B83D5' },
  uncertain: { bg: '#FBF2E2', fg: '#8F5E12', dot: '#D99A36' },
  strong: { bg: '#FBEAEA', fg: '#B03A3A', dot: '#D85B5B' },
};

/**
 * 서버 모델 이름 → 화면 표시 이름 (서버·저장 기록의 내부 이름은 바꾸지 않는다).
 * full = 결과 화면·기록 상세의 모델별 막대, short = 기록 목록의 모델 칩(좁은 공간).
 * 모르는 모델은 서버 이름 그대로 (모델 교체 시 앱을 고치지 않아도 되게).
 * univfd는 2026-11-14 commfor로 교체되었지만 이전에 저장된 기록을 표시하려고 남겨 둔다.
 */
const MODEL_NAMES: Record<string, { full: string; short: string }> = {
  commfor: { full: 'Community Forensics', short: 'CommFor' },
  aide: { full: 'AIDE', short: 'AIDE' },
  bfree: { full: 'B-Free', short: 'B-Free' },
  univfd: { full: 'UnivFD', short: 'UnivFD' },
};

// 자기 속성만 본다: 'constructor' 같은 이름이 와도 Object 기본 속성을 표시 이름으로 쓰지 않게
const known = (name: string) => (Object.prototype.hasOwnProperty.call(MODEL_NAMES, name) ? MODEL_NAMES[name] : null);

export function modelDisplayName(name: string): string {
  return known(name)?.full ?? name;
}

/** 기록 목록 칩처럼 좁은 곳에 쓰는 짧은 이름 */
export function modelShortName(name: string): string {
  return known(name)?.short ?? name;
}

/** 분석 기록 (이 기기에만 저장) */
export const HISTORY_EMPTY_TITLE = '아직 분석 기록이 없습니다.';
export const HISTORY_EMPTY_BODY = '이미지를 분석하면 결과가 이곳에 저장됩니다.';
export const HISTORY_SAVED_NOTE = '이 결과는 내 기록에 저장되었습니다. 이미지와 모델 주목 영역은 저장하지 않습니다.';
/** 메모 입력란 안내: 메모도 이 기기에만 저장된다 */
export const MEMO_PRIVACY_HINT = '이 기기에만 저장됩니다. 개인정보는 적지 않는 것을 권장합니다';
export const RECORD_NO_IMAGE_NOTE =
  '개인정보 보호를 위해 이미지와 모델 주목 영역은 저장하지 않아 다시 표시되지 않습니다. 아래는 분석 당시 저장된 판정 결과입니다.';

/** 기록 시각 표시: 2026.11.13 (금) 오후 3:05 — 기기 시간대 기준 */
export function formatRecordTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const days = ['일', '월', '화', '수', '목', '금', '토'];
  const h = d.getHours();
  const ampm = h < 12 ? '오전' : '오후';
  const h12 = h % 12 === 0 ? 12 : h % 12;
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')} (${days[d.getDay()]}) ${ampm} ${h12}:${mm}`;
}
