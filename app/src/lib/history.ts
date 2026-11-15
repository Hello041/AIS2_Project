// 분석 기록 (이 기기 내부에만 저장). 순수 함수만 둔다 → Node에서 검증 가능. 파일 입출력은 historyStore.ts.
//
// 개인정보 원칙 (CLAUDE.md, 2026-11 내 기록 요청):
// - 저장하는 것: 기록 ID, 분석 시각, 종합 판정, 모델별 판정 구간(name·band), '분석되지 않음' 모델 이름,
//   자동 제목, 사용자가 직접 입력한 제목·메모(선택).
// - 저장하지 않는 것: 이미지·썸네일·파일 경로(uri), 히트맵(PNG/base64), EXIF·GPS, 파일명, raw_score 등 응답의 나머지 값.
//   → toRecord()가 필요한 필드만 골라 새 객체를 만든다(응답 객체를 통째로 넣지 않는다).

import { BANDS, type AnalyzeResponse, type Band } from './types';

export const HISTORY_VERSION = 1;
/** 파일이 끝없이 커지지 않도록 최근 기록만 남긴다 */
export const HISTORY_MAX = 200;

export type HistoryRecord = {
  id: string;
  /** 분석이 끝난 시각 (ISO 8601, UTC) */
  analyzedAt: string;
  overall: Band;
  models: { name: string; band: Band }[];
  /** /health가 알렸지만 응답에 없던 모델 → 상세 화면에서 '분석되지 않음' */
  missing: string[];
  /** 저장할 때 만든 제목 "11월 14일 분석 #2" (나중에 다른 기록을 지워도 바뀌지 않게 저장) */
  autoTitle?: string;
  /** 사용자가 직접 정한 제목. 없으면 autoTitle을 보여 준다 */
  title?: string;
  /** 사용자 메모 (선택) */
  memo?: string;
};

export const TITLE_MAX = 40;
export const MEMO_MAX = 500;

/** 제목: 앞뒤 공백·줄바꿈·제어 문자를 정리하고 길이를 자른다. 비면 undefined(자동 제목 사용) */
export function cleanTitle(v: unknown): string | undefined {
  if (typeof v !== 'string') return undefined;
  const t = v.replace(/[\u0000-\u001F\u007F]+/g, ' ').replace(/\s+/g, ' ').trim();
  return t ? [...t].slice(0, TITLE_MAX).join('') : undefined;
}

/** 메모: 줄바꿈은 남기고(최대 연속 2줄) 다른 제어 문자는 지운다. 비면 undefined */
export function cleanMemo(v: unknown): string | undefined {
  if (typeof v !== 'string') return undefined;
  const t = v
    .replace(/\r\n?/g, '\n')
    .replace(/[\u0000-\u0009\u000B-\u001F\u007F]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  return t ? [...t].slice(0, MEMO_MAX).join('') : undefined;
}

const sameLocalDay = (a: Date, b: Date) =>
  a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

/** 자동 제목 "11월 14일 분석 #2": 같은 날(기기 시간대) 이미 저장된 기록 수 + 1 */
export function makeAutoTitle(existing: readonly HistoryRecord[], now: Date): string {
  const n = existing.filter((r) => sameLocalDay(new Date(r.analyzedAt), now)).length + 1;
  return `${now.getMonth() + 1}월 ${now.getDate()}일 분석 #${n}`;
}

/** 화면에 보여 줄 제목: 사용자 제목 → 자동 제목 → (예전 기록) 날짜로 만든 제목 */
export function displayTitle(rec: HistoryRecord): string {
  if (rec.title) return rec.title;
  if (rec.autoTitle) return rec.autoTitle;
  const d = new Date(rec.analyzedAt);
  return `${d.getMonth() + 1}월 ${d.getDate()}일 분석`;
}

/** 제목·메모 수정. 빈 값이면 지운다(제목은 자동 제목으로 돌아감). 판정 값은 바꾸지 않는다. */
export function editRecord(
  records: readonly HistoryRecord[],
  id: string,
  patch: { title?: string; memo?: string },
): HistoryRecord[] {
  return records.map((r) => {
    if (r.id !== id) return r;
    const { title: _t, memo: _m, ...rest } = r;
    const title = cleanTitle(patch.title);
    const memo = cleanMemo(patch.memo);
    return { ...rest, ...(title ? { title } : {}), ...(memo ? { memo } : {}) };
  });
}

export type HistoryFile = { v: typeof HISTORY_VERSION; records: HistoryRecord[] };

/** 기록 ID: 시각 + 난수 (기기 안에서만 쓰므로 충돌만 피하면 된다) */
export function newRecordId(now: Date, random: () => number = Math.random): string {
  const r = Math.floor(random() * 36 ** 8)
    .toString(36)
    .padStart(8, '0');
  return `${now.getTime().toString(36)}-${r}`;
}

/** 분석 응답 → 기록. 서버가 준 overall·band를 그대로 저장한다(다시 계산하지 않음). */
export function toRecord(
  res: AnalyzeResponse,
  expectedModels: readonly string[] | null,
  now: Date,
  id: string,
  autoTitle?: string,
): HistoryRecord {
  const models = res.models.map((m) => ({ name: String(m.name), band: m.band }));
  const present = new Set(models.map((m) => m.name));
  const missing = [...new Set((expectedModels ?? []).filter((n) => !present.has(n)))];
  const rec: HistoryRecord = { id, analyzedAt: now.toISOString(), overall: res.overall, models, missing };
  const t = cleanTitle(autoTitle);
  return t ? { ...rec, autoTitle: t } : rec;
}

const isBand = (v: unknown): v is Band => BANDS.includes(v as Band);

/** 저장된 값 하나를 검사한다. 규격과 다르면 null(목록에서 뺀다). 알 수 없는 필드는 버린다. */
export function parseRecord(v: unknown): HistoryRecord | null {
  if (!v || typeof v !== 'object') return null;
  const r = v as Record<string, unknown>;
  if (typeof r.id !== 'string' || r.id.length === 0 || r.id.length > 64) return null;
  if (typeof r.analyzedAt !== 'string' || Number.isNaN(Date.parse(r.analyzedAt))) return null;
  if (!isBand(r.overall)) return null;
  if (!Array.isArray(r.models) || r.models.length === 0) return null;
  const models: HistoryRecord['models'] = [];
  for (const m of r.models) {
    if (!m || typeof m !== 'object') return null;
    const mm = m as Record<string, unknown>;
    if (typeof mm.name !== 'string' || mm.name.length === 0 || !isBand(mm.band)) return null;
    models.push({ name: mm.name, band: mm.band });
  }
  const missing = Array.isArray(r.missing) ? r.missing.filter((n): n is string => typeof n === 'string') : [];
  const rec: HistoryRecord = { id: r.id, analyzedAt: r.analyzedAt, overall: r.overall, models, missing };
  // 선택 필드: 형식이 맞지 않으면 버린다 (예전 기록에는 없음)
  const autoTitle = cleanTitle(r.autoTitle);
  const title = cleanTitle(r.title);
  const memo = cleanMemo(r.memo);
  return {
    ...rec,
    ...(autoTitle ? { autoTitle } : {}),
    ...(title ? { title } : {}),
    ...(memo ? { memo } : {}),
  };
}

/** 최신순 정렬 + 중복 ID 제거 + 개수 제한 */
export function normalize(records: readonly HistoryRecord[]): HistoryRecord[] {
  const seen = new Set<string>();
  return [...records]
    .sort((a, b) => Date.parse(b.analyzedAt) - Date.parse(a.analyzedAt))
    .filter((r) => (seen.has(r.id) ? false : (seen.add(r.id), true)))
    .slice(0, HISTORY_MAX);
}

/** 파일 내용 → 기록 목록. 깨졌거나 버전이 다르면 빈 목록 (잘못된 기록을 결과처럼 보여 주지 않는다). */
export function parseHistoryFile(text: string): HistoryRecord[] {
  let v: unknown;
  try {
    v = JSON.parse(text);
  } catch {
    return [];
  }
  if (!v || typeof v !== 'object') return [];
  const f = v as Record<string, unknown>;
  if (f.v !== HISTORY_VERSION || !Array.isArray(f.records)) return [];
  return normalize(f.records.map(parseRecord).filter((r): r is HistoryRecord => r !== null));
}

export function serializeHistory(records: readonly HistoryRecord[]): string {
  const file: HistoryFile = { v: HISTORY_VERSION, records: normalize(records) };
  return JSON.stringify(file);
}

export function addRecord(records: readonly HistoryRecord[], rec: HistoryRecord): HistoryRecord[] {
  return normalize([rec, ...records.filter((r) => r.id !== rec.id)]);
}

export function removeRecord(records: readonly HistoryRecord[], id: string): HistoryRecord[] {
  return records.filter((r) => r.id !== id);
}

/** 목록·홈 카드용 한 줄 요약: "UnivFD 약함 · AIDE 강함 · B-Free 강함" */
export function modelSummary(rec: HistoryRecord, displayName: (n: string) => string, bandLabel: Record<Band, string>) {
  return rec.models.map((m) => ({ key: m.name, name: displayName(m.name), band: m.band, label: bandLabel[m.band] }));
}
