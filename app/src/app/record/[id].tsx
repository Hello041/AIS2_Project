import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { Button } from '@/components/Button';
import { confirmDeleteRecord } from '@/components/confirm';
import { colors, common, font, radius, space, typo } from '@/components/theme';
import { EmptyState, ModelBars, OverallCard } from '@/components/ui';
import { MEMO_MAX, TITLE_MAX, displayTitle, type HistoryRecord } from '@/lib/history';
import { updateRecordNote, useHistory } from '@/lib/historyStore';
import {
  GUIDE_ITEMS,
  MEMO_PRIVACY_HINT,
  MODELS_DIFFER_NOTE,
  MODELS_NOTICE,
  RECORD_NO_IMAGE_NOTE,
  formatRecordTime,
} from '@/lib/labels';
import { modelRows, overallView } from '@/lib/resultView';

// 기록 상세: 분석 당시 저장한 판정(종합·모델별 구간)을 그대로 보여 준다. 다시 계산하지 않는다.
// 이미지·모델 주목 영역은 저장하지 않으므로 표시하지 않는다. 제목·메모만 사용자가 고칠 수 있다.
export default function RecordScreen() {
  const router = useRouter();
  const { id, edit } = useLocalSearchParams<{ id: string; edit?: string }>();
  const { ready, records } = useHistory();
  const record = records.find((r) => r.id === id);
  const [editing, setEditing] = useState(edit === '1');

  if (!record) {
    return (
      <View style={[common.screen, styles.content]}>
        {ready && <EmptyState title="기록을 찾을 수 없습니다." body="삭제되었거나 저장되지 않은 기록입니다." />}
        <Button title="내 기록으로" variant="secondary" onPress={() => router.back()} />
      </View>
    );
  }

  const overall = overallView(record.overall);
  const rows = modelRows(record.models, record.missing);

  return (
    <KeyboardAvoidingView style={common.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        style={common.screen}
        contentContainerStyle={styles.content}
        contentInsetAdjustmentBehavior="automatic"
        keyboardShouldPersistTaps="handled">
        {editing ? (
          <NoteEditor record={record} onClose={() => setEditing(false)} />
        ) : (
          <NoteView record={record} onEdit={() => setEditing(true)} />
        )}

        <OverallCard overall={overall} />

        <View style={[common.card, styles.section]}>
          <Text style={typo.cardTitle}>모델별 분석 결과</Text>
          <ModelBars rows={rows} />
          <Text style={typo.caption}>{MODELS_NOTICE}</Text>
          <Text style={typo.caption}>{MODELS_DIFFER_NOTE}</Text>
        </View>

        <View style={styles.privacyNote}>
          <Text style={styles.privacyText}>{RECORD_NO_IMAGE_NOTE}</Text>
        </View>

        <View style={styles.guide}>
          {GUIDE_ITEMS.map((g) => (
            <Text key={g} style={typo.caption}>
              · {g}
            </Text>
          ))}
        </View>

        <Button title="이 기록 삭제" variant="danger" onPress={() => confirmDeleteRecord(record.id, () => router.back())} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

/** 제목·시각·메모 보기 + 편집 버튼 */
function NoteView({ record, onEdit }: { record: HistoryRecord; onEdit: () => void }) {
  const custom = !!record.title;
  return (
    <View style={[common.card, styles.noteCard]}>
      <View style={styles.noteHeader}>
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={styles.title} accessibilityRole="header">
            {displayTitle(record)}
          </Text>
          <Text style={typo.caption}>
            분석 일시 · {formatRecordTime(record.analyzedAt)}
            {custom ? '' : ' · 자동 제목'}
          </Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="제목과 메모 편집"
          onPress={onEdit}
          hitSlop={8}
          style={({ pressed }) => [styles.editBtn, pressed && { backgroundColor: colors.track }]}>
          <Text style={styles.editText}>편집</Text>
        </Pressable>
      </View>
      {record.memo ? (
        <View style={styles.memoBox}>
          <Text style={typo.body}>{record.memo}</Text>
        </View>
      ) : (
        <Pressable accessibilityRole="button" onPress={onEdit} style={styles.addMemo}>
          <Text style={styles.addMemoText}>+ 메모 추가</Text>
        </Pressable>
      )}
    </View>
  );
}

/** 제목·메모 편집. 빈 제목으로 저장하면 자동 제목으로 돌아간다. 판정 값은 고칠 수 없다. */
function NoteEditor({ record, onClose }: { record: HistoryRecord; onClose: () => void }) {
  const [title, setTitle] = useState(record.title ?? '');
  const [memo, setMemo] = useState(record.memo ?? '');
  const [saving, setSaving] = useState(false);
  const autoTitle = record.autoTitle ?? displayTitle({ ...record, title: undefined });

  async function onSave() {
    setSaving(true);
    try {
      await updateRecordNote(record.id, { title, memo });
      onClose();
    } catch {
      Alert.alert('저장하지 못했습니다', '잠시 후 다시 시도해 주세요.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={[common.card, styles.noteCard]}>
      <Text style={typo.cardTitle} accessibilityRole="header">
        제목·메모 편집
      </Text>

      <View style={styles.field}>
        <Text style={styles.label}>제목</Text>
        <TextInput
          value={title}
          onChangeText={setTitle}
          placeholder={autoTitle}
          placeholderTextColor={colors.tabInactive}
          maxLength={TITLE_MAX}
          returnKeyType="done"
          style={styles.input}
          accessibilityLabel="제목"
          accessibilityHint={`비워 두면 자동 제목 '${autoTitle}'을 씁니다`}
        />
        <Text style={styles.help}>
          비워 두면 자동 제목을 씁니다 · {[...title].length}/{TITLE_MAX}
        </Text>
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>메모 (선택)</Text>
        <TextInput
          value={memo}
          onChangeText={setMemo}
          placeholder="예: 커뮤니티에서 본 사진"
          placeholderTextColor={colors.tabInactive}
          maxLength={MEMO_MAX}
          multiline
          textAlignVertical="top"
          style={[styles.input, styles.memoInput]}
          accessibilityLabel="메모"
        />
        <Text style={styles.help}>
          {MEMO_PRIVACY_HINT} · {[...memo].length}/{MEMO_MAX}
        </Text>
      </View>

      <View style={styles.editActions}>
        <View style={{ flex: 1 }}>
          <Button title="취소" variant="secondary" onPress={onClose} disabled={saving} />
        </View>
        <View style={{ flex: 1 }}>
          <Button title={saving ? '저장 중…' : '저장'} onPress={onSave} disabled={saving} />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.screen, gap: space.gap, paddingBottom: 40 },
  section: { gap: 14 },
  noteCard: { gap: 12 },
  noteHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  title: { ...font.bold, fontSize: 20, lineHeight: 28, color: colors.text },
  editBtn: {
    minHeight: 40,
    paddingHorizontal: 14,
    justifyContent: 'center',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  editText: { ...font.semibold, fontSize: 14, color: colors.primary },
  memoBox: { backgroundColor: colors.background, borderRadius: 10, padding: 12 },
  addMemo: { minHeight: 40, justifyContent: 'center', alignSelf: 'flex-start' },
  addMemoText: { ...font.semibold, fontSize: 14, color: colors.primary },
  field: { gap: 6 },
  label: { ...font.semibold, fontSize: 14, color: colors.text },
  input: {
    ...font.regular,
    fontSize: 16,
    color: colors.text,
    minHeight: 48,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.button,
    paddingHorizontal: 14,
    paddingVertical: 12,
    backgroundColor: colors.surface,
  },
  memoInput: { minHeight: 110 },
  help: { ...font.regular, fontSize: 12, lineHeight: 17, color: colors.textMuted },
  editActions: { flexDirection: 'row', gap: 10, marginTop: 4 },
  privacyNote: {
    backgroundColor: colors.primarySoft,
    borderRadius: 12,
    padding: 14,
  },
  privacyText: { ...font.regular, fontSize: 13, lineHeight: 19, color: colors.navy },
  guide: { gap: 4, paddingHorizontal: 4 },
});
