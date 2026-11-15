import { useRouter } from 'expo-router';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { confirmClearHistory, confirmDeleteRecord } from '@/components/confirm';
import { RecordCard } from '@/components/RecordCard';
import { colors, common, font, space, typo } from '@/components/theme';
import { EmptyState, ScreenHeader } from '@/components/ui';
import { useHistory } from '@/lib/historyStore';
import { HISTORY_EMPTY_BODY, HISTORY_EMPTY_TITLE } from '@/lib/labels';

// 내 기록: 이 기기에 저장된 분석 결과 목록 (최신순). 이미지는 저장하지 않으므로 판정 결과만 보여 준다.
export default function HistoryScreen() {
  const router = useRouter();
  const { ready, records } = useHistory();

  return (
    <SafeAreaView style={common.screen} edges={['top', 'left', 'right']}>
      <FlatList
        data={records}
        keyExtractor={(r) => r.id}
        contentInsetAdjustmentBehavior="automatic"
        contentContainerStyle={styles.content}
        ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
        ListHeaderComponent={
          <View style={styles.header}>
            <ScreenHeader
              title="내 기록"
              subtitle="이 기기에 저장된 분석 결과"
              right={
                records.length > 0 ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityHint="확인 후 이 기기의 분석 기록을 모두 삭제합니다"
                    onPress={() => confirmClearHistory(records.length)}
                    hitSlop={8}
                    style={styles.clearBtn}>
                    <Text style={styles.clearText}>전체 삭제</Text>
                  </Pressable>
                ) : undefined
              }
            />
            {records.length > 0 && (
              <Text style={typo.caption}>
                {records.length}개 · 기록을 길게 누르면 삭제할 수 있습니다.
              </Text>
            )}
          </View>
        }
        ListEmptyComponent={ready ? <EmptyState title={HISTORY_EMPTY_TITLE} body={HISTORY_EMPTY_BODY} /> : undefined}
        renderItem={({ item }) => (
          <RecordCard
            record={item}
            onPress={() => router.push({ pathname: '/record/[id]', params: { id: item.id } })}
            onLongPress={() => confirmDeleteRecord(item.id)}
          />
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.screen, paddingTop: 12, paddingBottom: 32 },
  header: { gap: 8, marginBottom: 16 },
  clearBtn: {
    minHeight: 40,
    paddingHorizontal: 12,
    justifyContent: 'center',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  clearText: { ...font.semibold, fontSize: 14, color: colors.error },
});
