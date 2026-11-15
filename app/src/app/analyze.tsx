import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { colors, common, font, space } from '@/components/theme';
import { ANALYSIS_STEPS, ApiError, analyzeImage } from '@/lib/api';
import { ANALYZE_TIMEOUT_MS } from '@/lib/config';
import { createRecord, saveRecord } from '@/lib/historyStore';
import { session } from '@/lib/session';

type Failure = { message: string; retryable: boolean };

// 분석 중 화면 (계획서 §6-2): 단계 표시, 2분 타임아웃, 실패 시 안내·재시도.
export default function AnalyzeScreen() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [detail, setDetail] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [elapsedSec, setElapsedSec] = useState(0);

  // 실제 경과 시간만 보여 준다. 서버가 진행률을 주지 않으므로 퍼센트는 표시하지 않는다.
  useEffect(() => {
    if (failure) return undefined;
    setElapsedSec(0);
    const started = Date.now();
    const t = setInterval(() => setElapsedSec(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(t);
  }, [attempt, failure]);

  useEffect(() => {
    const image = session.getImage();
    if (!image) {
      setFailure({ message: '선택한 이미지가 없습니다', retryable: false });
      return;
    }

    const controller = new AbortController();
    let timedOut = false;
    let left = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, ANALYZE_TIMEOUT_MS);

    setFailure(null);
    setStep(0);
    setDetail(null);
    analyzeImage(image, controller.signal, setStep, (text) => {
      if (!left) setDetail(text);
    })
      .then((outcome) => {
        // 내 기록 저장 (판정 값만). 실패해도 결과 화면은 그대로 보여 준다 → 기다리지 않고 오류만 삼킨다.
        let recordId: string | null = null;
        try {
          const rec = createRecord(outcome);
          recordId = rec.id;
          saveRecord(rec).catch(() => undefined);
        } catch {
          recordId = null;
        }
        session.setOutcome(outcome, recordId);
        router.replace('/result');
      })
      .catch((e: unknown) => {
        if (left) return; // 사용자가 뒤로 가서 취소함
        const err = timedOut ? new ApiError('timeout') : e instanceof ApiError ? e : new ApiError('server');
        setFailure({ message: err.message, retryable: err.retryable });
      })
      .finally(() => clearTimeout(timer));

    return () => {
      left = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [attempt, router]);

  if (failure) {
    return (
      <View style={styles.container}>
        <View style={[common.card, styles.failCard]}>
          <Text style={styles.failTitle}>{failure.message}</Text>
          <Text style={styles.failHint}>
            {failure.retryable
              ? '잠시 후 다시 시도해 주세요.'
              : '다른 이미지를 선택해 주세요.'}
          </Text>
        </View>
        <View style={styles.actions}>
          {failure.retryable && <Button title="다시 시도" onPress={() => setAttempt((a) => a + 1)} />}
          <Button
            title="다른 이미지 선택"
            variant={failure.retryable ? 'secondary' : 'primary'}
            onPress={() => router.back()}
          />
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[common.card, styles.stepsCard]}>
        {ANALYSIS_STEPS.map((label, i) => {
          const state = i < step ? 'done' : i === step ? 'active' : 'todo';
          return (
            <View key={label} style={styles.stepRow}>
              <View style={styles.stepIcon}>
                {state === 'active' ? (
                  <ActivityIndicator color={colors.primary} />
                ) : (
                  <View
                    style={[
                      styles.stepDot,
                      state === 'done' && { backgroundColor: colors.primary, borderColor: colors.primary },
                    ]}
                  />
                )}
              </View>
              <View style={styles.stepLabel}>
                <Text
                  style={[
                    styles.stepText,
                    state === 'todo' && { color: colors.textFaint },
                    state === 'active' && font.bold,
                  ]}>
                  {label}
                </Text>
                {state === 'active' && !!detail && <Text style={styles.stepDetail}>{detail}</Text>}
              </View>
            </View>
          );
        })}
      </View>
      <View style={styles.waitBox} accessibilityLiveRegion="polite">
        <Text style={styles.elapsed}>경과 시간 {elapsedSec}초</Text>
        <Text style={styles.note}>
          {elapsedSec < 60
            ? '여러 AI 모델이 차례로 분석합니다. 보통 20초 안팎 걸립니다 (최대 2분).'
            : '평소보다 오래 걸리고 있습니다. 최대 2분까지 기다린 뒤 결과가 없으면 다시 시도할 수 있습니다.'}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: space.screen, gap: space.gap, backgroundColor: colors.background },
  stepsCard: { gap: 18 },
  stepRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  stepIcon: { width: 24, alignItems: 'center' },
  stepDot: {
    width: 14,
    height: 14,
    borderRadius: 7,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  stepLabel: { flex: 1, gap: 2 },
  stepText: { ...font.medium, fontSize: 16, lineHeight: 22, color: colors.text },
  stepDetail: { ...font.regular, fontSize: 13, lineHeight: 19, color: colors.textMuted },
  waitBox: { gap: 6, alignItems: 'center' },
  elapsed: { ...font.semibold, fontSize: 15, color: colors.text },
  note: { ...font.regular, fontSize: 14, lineHeight: 21, color: colors.textMuted, textAlign: 'center' },
  failCard: { gap: 8 },
  failTitle: { ...font.bold, fontSize: 19, lineHeight: 26, color: colors.error },
  failHint: { ...font.regular, fontSize: 15, lineHeight: 22, color: colors.textMuted },
  actions: { gap: 10 },
});
