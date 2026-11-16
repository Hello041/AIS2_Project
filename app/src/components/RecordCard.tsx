import { Pressable, StyleSheet, Text, View } from 'react-native';

import { displayTitle, type HistoryRecord } from '@/lib/history';
import { OVERALL_LABEL, SEGMENT_LABEL, formatRecordTime, modelDisplayName, modelShortName } from '@/lib/labels';

import { colors, common, font, typo } from './theme';
import { BandBadge, Chevron, ModelChip } from './ui';

/** 기록 목록 한 줄: 제목, 시각, 종합 판정, 모델별 칩, (메모 첫 줄), 화살표. 누르면 상세. */
export function RecordCard({
  record,
  onPress,
  onLongPress,
}: {
  record: HistoryRecord;
  onPress: () => void;
  /** 길게 눌러 삭제 (내 기록 화면) */
  onLongPress?: () => void;
}) {
  const title = displayTitle(record);
  const time = formatRecordTime(record.analyzedAt);
  const summary = record.models.map((m) => `${modelDisplayName(m.name)} ${SEGMENT_LABEL[m.band]}`).join(', ');
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${title}. ${time}, 종합 판정 ${OVERALL_LABEL[record.overall]}. ${summary}${record.memo ? `. 메모 있음` : ''}`}
      accessibilityHint="기록 상세 보기"
      onPress={onPress}
      onLongPress={onLongPress}
      accessibilityActions={onLongPress ? [{ name: 'longpress', label: '이 기록 삭제' }] : undefined}
      onAccessibilityAction={(e) => e.nativeEvent.actionName === 'longpress' && onLongPress?.()}
      style={({ pressed }) => [common.card, styles.card, pressed && { backgroundColor: colors.track }]}>
      <View style={styles.body}>
        <View style={{ gap: 2 }}>
          <Text style={styles.title} numberOfLines={1}>
            {title}
          </Text>
          <Text style={typo.caption}>{time}</Text>
        </View>
        <BandBadge band={record.overall} size="sm" />
        <View style={styles.chips}>
          {record.models.map((m) => (
            <ModelChip key={m.name} name={modelShortName(m.name)} band={m.band} />
          ))}
        </View>
        {!!record.memo && (
          <Text style={styles.memo} numberOfLines={1}>
            {record.memo.split('\n')[0]}
          </Text>
        )}
      </View>
      <Chevron />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 14 },
  body: { flex: 1, gap: 8 },
  title: { ...font.semibold, fontSize: 16, lineHeight: 22, color: colors.text },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  memo: { ...font.regular, fontSize: 13, lineHeight: 19, color: colors.textMuted },
});
