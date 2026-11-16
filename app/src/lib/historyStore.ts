// 분석 기록 저장소: 앱 문서 폴더의 JSON 파일 하나 (expo-file-system, 이미 쓰는 패키지).
// - 이 기기 안에만 있다. 서버로 보내거나 동기화하지 않는다.
// - 앱을 다시 실행해도 남는다(문서 폴더는 OS가 임의로 지우지 않음). 앱을 삭제하면 함께 지워진다.
// - 화면들은 useHistory()로 같은 목록을 구독한다 → 저장·삭제 즉시 홈·내 기록 화면이 함께 바뀐다.

import { File, Paths } from 'expo-file-system';
import { useEffect, useSyncExternalStore } from 'react';

import type { AnalysisOutcome } from './api';
import {
  addRecord,
  editRecord,
  makeAutoTitle,
  newRecordId,
  parseHistoryFile,
  removeRecord,
  serializeHistory,
  toRecord,
  type HistoryRecord,
} from './history';

const FILE_NAME = 'analysis-history.json';

type State = { ready: boolean; records: HistoryRecord[] };
let state: State = { ready: false, records: [] };
const listeners = new Set<() => void>();
let loading: Promise<void> | null = null;
let writeQueue: Promise<void> = Promise.resolve();

function setState(next: State) {
  state = next;
  listeners.forEach((l) => l());
}

function historyFile() {
  return new File(Paths.document, FILE_NAME);
}

/** 파일에서 한 번만 읽는다. 읽기 실패·깨진 파일은 빈 목록으로 시작한다. */
export function loadHistory(): Promise<void> {
  if (!loading) {
    loading = (async () => {
      let records: HistoryRecord[] = [];
      try {
        const f = historyFile();
        if (f.exists) records = parseHistoryFile(await f.text());
      } catch {
        records = [];
      }
      setState({ ready: true, records });
    })();
  }
  return loading;
}

/** 쓰기를 차례로 실행한다 (동시에 두 번 쓰면 나중 내용이 앞의 내용을 덮을 수 있어서) */
function persist(records: HistoryRecord[]): Promise<void> {
  const text = serializeHistory(records);
  const run = writeQueue.then(async () => {
    const f = historyFile();
    if (!f.exists) f.create({ intermediates: true });
    await f.write(text);
  });
  writeQueue = run.catch(() => undefined);
  return run;
}

/** 분석 결과 → 저장할 기록 (판정 값만. 이미지·히트맵·경로는 넣지 않는다) */
export function createRecord(outcome: AnalysisOutcome, now = new Date()): HistoryRecord {
  return toRecord(outcome.result, outcome.expectedModels, now, newRecordId(now), makeAutoTitle(state.records, now));
}

/**
 * 기록을 이 기기에 저장한다. 목록에는 바로 보이고, 파일 저장에 실패하면 목록에서 다시 빼고 reject한다.
 * 호출한 쪽은 실패해도 결과 화면을 그대로 보여 준다 (analyze.tsx).
 */
export async function saveRecord(rec: HistoryRecord): Promise<void> {
  await loadHistory();
  setState({ ready: true, records: addRecord(state.records, rec) });
  try {
    await persist(state.records);
  } catch (e) {
    setState({ ready: true, records: removeRecord(state.records, rec.id) });
    throw e;
  }
}

/** 제목·메모 수정 (판정 값은 그대로). 저장에 실패하면 이전 값으로 되돌리고 reject */
export async function updateRecordNote(id: string, patch: { title?: string; memo?: string }): Promise<void> {
  await loadHistory();
  const before = state.records;
  setState({ ready: true, records: editRecord(before, id, patch) });
  try {
    await persist(state.records);
  } catch (e) {
    setState({ ready: true, records: before });
    throw e;
  }
}

export async function deleteRecord(id: string): Promise<void> {
  await loadHistory();
  const before = state.records;
  setState({ ready: true, records: removeRecord(before, id) });
  try {
    await persist(state.records);
  } catch (e) {
    setState({ ready: true, records: before });
    throw e;
  }
}

export async function clearHistory(): Promise<void> {
  await loadHistory();
  const before = state.records;
  setState({ ready: true, records: [] });
  try {
    await persist([]);
  } catch (e) {
    setState({ ready: true, records: before });
    throw e;
  }
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

/** 기록 목록 (최신순). 처음 쓰일 때 파일을 읽는다. */
export function useHistory(): State {
  const s = useSyncExternalStore(subscribe, () => state);
  useEffect(() => {
    void loadHistory();
  }, []);
  return s;
}
