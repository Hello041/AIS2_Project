import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { RecordCard } from '@/components/RecordCard';
import { colors, common, font, space, typo } from '@/components/theme';
import { EmptyState, Logo, SectionLabel } from '@/components/ui';
import { ApiError, checkHealth } from '@/lib/api';
import { API_BASE_URL, HEALTH_TIMEOUT_MS, USE_MOCK } from '@/lib/config';
import { useHistory } from '@/lib/historyStore';
import { pickImage } from '@/lib/image';
import { HISTORY_EMPTY_TITLE } from '@/lib/labels';
import { session } from '@/lib/session';

type Health =
  | { state: 'checking' }
  | { state: 'ok'; models: string[] }
  | { state: 'error'; message: string };

const RECENT_COUNT = 2;

export default function HomeScreen() {
  const router = useRouter();
  const [health, setHealth] = useState<Health>({ state: 'checking' });
  const [checkCount, setCheckCount] = useState(0);
  const [pickError, setPickError] = useState('');
  const [picking, setPicking] = useState(false);
  const history = useHistory();
  const recent = history.records.slice(0, RECENT_COUNT);

  // 홈 화면에 들어올 때마다 /health로 연결 상태를 확인한다 (계획서 §6).
  useFocusEffect(
    useCallback(() => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
      setHealth({ state: 'checking' });
      checkHealth(controller.signal)
        .then((h) => setHealth({ state: 'ok', models: h.models }))
        .catch((e) => {
          if (e instanceof ApiError && e.kind === 'aborted' && !controller.signal.aborted) return;
          const message =
            e instanceof ApiError && e.kind === 'not_configured' ? e.message : '서버에 연결할 수 없습니다';
          setHealth({ state: 'error', message });
        })
        .finally(() => clearTimeout(timer));
      return () => {
        clearTimeout(timer);
        controller.abort();
      };
    }, [checkCount]),
  );

  async function onPick() {
    setPickError('');
    setPicking(true);
    try {
      const r = await pickImage();
      if (r.status === 'error') setPickError(r.message);
      if (r.status === 'ok') {
        session.setImage(r.image);
        router.push('/analyze');
      }
    } catch {
      setPickError('이미지를 불러오지 못했습니다');
    } finally {
      setPicking(false);
    }
  }

  const dotColor =
    health.state === 'ok' ? colors.ok : health.state === 'error' ? colors.error : colors.tabInactive;
  const statusText =
    health.state === 'checking'
      ? '연결 확인 중'
      : health.state === 'ok'
        ? `연결됨 · 모델 ${health.models.length}개`
        : '연결 안 됨';

  return (
    <SafeAreaView style={common.screen} edges={['top', 'left', 'right']}>
      <ScrollView contentContainerStyle={styles.content} contentInsetAdjustmentBehavior="automatic">
        {/* 상단: 로고·서비스명, 서버 연결 상태 */}
        <View style={styles.topBar}>
          <View style={styles.brand}>
            <Logo size={36} />
            <Text style={styles.brandName}>TraceLens</Text>
          </View>
          <View
            style={styles.statusPill}
            accessible
            accessibilityLabel={`서버 ${statusText}`}
            accessibilityLiveRegion="polite">
            <View style={[styles.dot, { backgroundColor: dotColor }]} />
            <Text style={styles.statusText} numberOfLines={1}>
              {statusText}
            </Text>
          </View>
        </View>

        {health.state === 'error' && (
          <View style={[common.card, styles.errorCard]}>
            <Text style={[typo.bodyStrong, { color: colors.error }]}>{health.message}</Text>
            <Text style={typo.caption}>
              {API_BASE_URL
                ? `주소: ${API_BASE_URL}\n휴대폰과 노트북이 같은 Wi-Fi인지, 서버가 켜져 있는지 확인해 주세요.`
                : 'app/.env에 API_BASE_URL을 적고 Expo를 다시 시작해 주세요.'}
            </Text>
            <Button title="다시 확인" variant="secondary" onPress={() => setCheckCount((c) => c + 1)} />
          </View>
        )}
        {USE_MOCK && <Text style={typo.caption}>가짜 응답 모드입니다 (API_BASE_URL=mock)</Text>}

        {/* 메인: 문구 + 이미지 선택 */}
        <View style={[common.card, styles.hero]}>
          <Text style={typo.hero} accessibilityRole="header">
            이 이미지,{'\n'}AI가 만들었을까요?
          </Text>
          <Text style={typo.muted}>이미지를 업로드하고 AI 생성 여부를 분석해 보세요.</Text>
          <View style={styles.pick}>
            <Button
              title={picking ? '여는 중…' : '이미지 선택하기'}
              onPress={onPick}
              disabled={picking}
              accessibilityHint="사진 보관함에서 분석할 이미지 한 장을 고릅니다"
            />
            <Text style={[typo.caption, { textAlign: 'center' }]}>
              JPG · PNG · WebP 지원{'\n'}iPhone HEIC 사진은 자동으로 변환해 분석합니다
            </Text>
          </View>
          {!!pickError && (
            <Text style={styles.error} accessibilityRole="alert">
              {pickError}
            </Text>
          )}
        </View>

        {/* 최근 분석 기록 (최대 2개) */}
        <View style={styles.recent}>
          <SectionLabel
            right={
              history.records.length > 0 ? (
                <Pressable
                  accessibilityRole="link"
                  onPress={() => router.navigate('/history')}
                  hitSlop={12}
                  style={styles.moreLink}>
                  <Text style={styles.moreText}>전체 보기</Text>
                </Pressable>
              ) : undefined
            }>
            최근 분석 기록
          </SectionLabel>
          {history.ready && recent.length === 0 && <EmptyState title={HISTORY_EMPTY_TITLE} />}
          {recent.map((r) => (
            <RecordCard
              key={r.id}
              record={r}
              onPress={() => router.push({ pathname: '/record/[id]', params: { id: r.id } })}
            />
          ))}
        </View>

        <Text style={styles.disclaimer}>
          분석 결과는 참고 정보이며 AI 생성 여부를 단정하지 않습니다. 선택한 이미지는 분석에만 쓰이고 서버에 저장되지
          않습니다.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.screen, paddingTop: 12, paddingBottom: 32, gap: 20 },
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 10, flexShrink: 1 },
  brandName: { ...font.bold, fontSize: 18, lineHeight: 24, color: colors.navy },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 999,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    flexShrink: 1,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { ...font.medium, fontSize: 12, color: colors.textMuted, flexShrink: 1 },
  errorCard: { gap: 10 },
  hero: { gap: 12, paddingVertical: 24 },
  pick: { gap: 10, marginTop: 8 },
  error: {
    ...font.medium,
    fontSize: 14,
    lineHeight: 20,
    color: colors.error,
    backgroundColor: colors.errorBg,
    padding: 12,
    borderRadius: 10,
    overflow: 'hidden',
  },
  recent: { gap: 10 },
  moreLink: { minHeight: 32, justifyContent: 'center' },
  moreText: { ...font.semibold, fontSize: 14, color: colors.primary },
  disclaimer: { ...font.regular, fontSize: 12, lineHeight: 18, color: colors.textMuted },
});
