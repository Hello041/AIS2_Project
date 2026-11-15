import { Alert } from 'react-native';

import { clearHistory, deleteRecord } from '@/lib/historyStore';

const failed = () => Alert.alert('삭제하지 못했습니다', '잠시 후 다시 시도해 주세요.');

/** 기록 하나 삭제 (확인 후). 삭제되면 onDone */
export function confirmDeleteRecord(id: string, onDone?: () => void) {
  Alert.alert('이 기록을 삭제할까요?', '삭제한 기록은 되돌릴 수 없습니다.', [
    { text: '취소', style: 'cancel' },
    {
      text: '삭제',
      style: 'destructive',
      onPress: () => {
        deleteRecord(id).then(() => onDone?.(), failed);
      },
    },
  ]);
}

/** 전체 기록 삭제 (반드시 확인 팝업을 거친다) */
export function confirmClearHistory(count: number) {
  Alert.alert('전체 기록을 삭제할까요?', `이 기기에 저장된 분석 기록 ${count}개가 모두 삭제되며 되돌릴 수 없습니다.`, [
    { text: '취소', style: 'cancel' },
    {
      text: '전체 삭제',
      style: 'destructive',
      onPress: () => {
        clearHistory().catch(failed);
      },
    },
  ]);
}
