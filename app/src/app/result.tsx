import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { colors, common, font, space, typo } from '@/components/theme';
import { ModelBars, OverallCard } from '@/components/ui';
import { useHistory } from '@/lib/historyStore';
import {
  GUIDE_ITEMS,
  HEATMAP_LEGEND_ITEMS,
  HEATMAP_NOTICE,
  HEATMAP_RELATIVE_NOTE,
  HISTORY_SAVED_NOTE,
  MODELS_DIFFER_NOTE,
  MODELS_NOTICE,
  heatmapCoverageNote,
} from '@/lib/labels';
import { buildResultView, type HeatmapView } from '@/lib/resultView';
import { session } from '@/lib/session';

// 결과 화면 (계획서 §6-3, 시안 BIN0002).
// 종합 판정 = 서버 overall, 모델별 = 서버 band 그대로. raw_score·overall_method는 표시하지 않는다.
export default function ResultScreen() {
  const router = useRouter();
  const [guideOpen, setGuideOpen] = useState(false);
  const outcome = session.getOutcome();
  const recordId = session.getRecordId();
  const { records } = useHistory();
  const saved = !!recordId && records.some((r) => r.id === recordId);

  if (!outcome) {
    return (
      <View style={[common.screen, { padding: space.screen, gap: space.gap }]}>
        <Text style={typo.body}>표시할 결과가 없습니다.</Text>
        <Button title="홈으로" onPress={() => router.dismissAll()} />
      </View>
    );
  }

  const view = buildResultView(outcome.result, outcome.expectedModels, outcome.preprocess);

  return (
    <ScrollView style={common.screen} contentContainerStyle={styles.content} contentInsetAdjustmentBehavior="automatic">
      {/* 종합 판정: 화면에서 가장 먼저 보이는 영역 (가운데 정렬) */}
      <OverallCard overall={view.overall} />

      {/* 모델별 분석 결과: 3칸 막대, 서버 band에 해당하는 칸 하나만 강조 */}
      <View style={[common.card, styles.section]}>
        <Text style={typo.cardTitle}>모델별 분석 결과</Text>
        <ModelBars rows={view.models} />
        <Text style={typo.caption}>{MODELS_NOTICE}</Text>
        <Text style={typo.caption}>{MODELS_DIFFER_NOTE}</Text>
      </View>

      {/* 모델 주목 영역: 서버가 만든 경우에만. 없거나 잘못되면 이 영역만 숨긴다 */}
      {view.heatmap && <HeatmapSection heatmap={view.heatmap} originalUri={session.getImage()?.uri} />}

      {/* 분석에 쓴 이미지: 앱 전처리의 실제 처리 내역 */}
      {view.preprocess && (
        <View style={[common.card, styles.section]}>
          <Text style={typo.cardTitle}>분석한 이미지</Text>
          <Text style={typo.body}>{view.preprocess.headline}</Text>
          {view.preprocess.details.map((d) => (
            <Text key={d} style={typo.muted}>
              · {d}
            </Text>
          ))}
        </View>
      )}

      {/* 출처 확인: provenance가 null이면 '준비 중' */}
      <View style={[common.card, styles.section]}>
        <Text style={typo.cardTitle}>출처 확인</Text>
        <Text style={typo.body}>{view.provenance.title}</Text>
        {view.provenance.detail && <Text style={typo.caption}>{view.provenance.detail}</Text>}
      </View>

      {/* 하단 안내: 서버 disclaimer는 항상, 상세 참고 사항은 접어 둔다 */}
      <View style={styles.guide}>
        <Text style={typo.muted}>{view.disclaimer}</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ expanded: guideOpen }}
          onPress={() => setGuideOpen((o) => !o)}
          style={styles.guideToggle}>
          <Text style={styles.guideToggleText}>{guideOpen ? '참고 사항 접기' : '결과를 볼 때 참고할 점 보기'}</Text>
        </Pressable>
        {guideOpen &&
          GUIDE_ITEMS.map((g) => (
            <Text key={g} style={typo.muted}>
              · {g}
            </Text>
          ))}
      </View>

      {saved && (
        <View style={styles.savedNote}>
          <Text style={styles.savedText}>{HISTORY_SAVED_NOTE}</Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => router.push({ pathname: '/record/[id]', params: { id: recordId!, edit: '1' } })}
            style={styles.savedLink}>
            <Text style={styles.guideToggleText}>제목·메모 추가</Text>
          </Pressable>
        </View>
      )}

      <Button title="다른 이미지 분석" onPress={() => router.dismissAll()} />
    </ScrollView>
  );
}

// 서버 heatmap.colormap()을 0~1에서 9곳 뽑은 색 (Turbo 기반): 낮음(파랑) → 중간(노랑) → 높음(빨강)
// 판정 구간 색(BAND_COLOR)과는 다른 의미(모델 주목 강도)다.
const LEGEND_COLORS = ['#4666EB', '#26B9E4', '#3DF196', '#91FB53', '#EAD32E', '#FFAB24', '#FF7B1C', '#E74A13', '#BA2208'];
const LEGEND_SWATCH = { blue: LEGEND_COLORS[0], yellow: LEGEND_COLORS[4], red: LEGEND_COLORS[8] };

function HeatmapSection({ heatmap, originalUri }: { heatmap: HeatmapView; originalUri?: string }) {
  const [originalFailed, setOriginalFailed] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const showOriginal = !!originalUri && !originalFailed;
  const [heatFailed, setHeatFailed] = useState(false);
  if (heatFailed) return null; // PNG를 그리지 못하면 영역 전체를 숨긴다
  return (
    <View style={[common.card, styles.section]}>
      <Text style={typo.cardTitle} accessibilityRole="header">
        모델 주목 영역 · {heatmap.modelName}
      </Text>
      {/* 주요 안내: 항상 보인다 */}
      <Text style={typo.bodyStrong}>{HEATMAP_NOTICE}</Text>
      <View style={styles.heatRow}>
        {showOriginal && (
          <View style={styles.heatCol}>
            <Image
              source={{ uri: originalUri }}
              style={[styles.heatImage, { aspectRatio: heatmap.aspect }]}
              resizeMode="cover"
              onError={() => setOriginalFailed(true)}
              accessibilityLabel="원본 이미지"
            />
            <Text style={styles.heatCaption}>원본</Text>
          </View>
        )}
        <View style={styles.heatCol}>
          <Image
            source={{ uri: heatmap.uri }}
            style={[styles.heatImage, { aspectRatio: heatmap.aspect }]}
            resizeMode="contain"
            onError={() => setHeatFailed(true)}
            accessibilityLabel={`${heatmap.modelName} 모델 주목 영역`}
          />
          <Text style={styles.heatCaption}>모델 주목 영역</Text>
        </View>
      </View>

      {/* 범례: 색 = 이미지 안에서의 상대적 주목 강도(파랑 낮음 → 노랑 중간 → 빨강 높음), 회색 빗금 = 분석 범위 밖 */}
      <View style={styles.legend}>
        <View
          style={styles.legendScale}
          accessible
          accessibilityLabel="주목 강도 범례: 파란색은 상대적으로 낮은 주목, 노란색은 중간, 빨간색은 높은 주목">
          <Text style={styles.legendTitle}>주목 강도</Text>
          <View style={styles.legendRamp}>
            {LEGEND_COLORS.map((c) => (
              <View key={c} style={[styles.legendStep, { backgroundColor: c }]} />
            ))}
          </View>
          <View style={styles.legendLabels}>
            <Text style={styles.legendText}>낮음</Text>
            <Text style={styles.legendText}>중간</Text>
            <Text style={styles.legendText}>높음</Text>
          </View>
        </View>
        <View style={styles.legendItem}>
          <View style={styles.hatchSwatch}>
            {[0, 1, 2, 3].map((i) => (
              <View key={i} style={[styles.hatchLine, { left: i * 6 - 6 }]} />
            ))}
          </View>
          <Text style={styles.legendText}>분석 범위 밖</Text>
        </View>
      </View>

      {/* 색 설명: 한 줄에 하나씩 */}
      <View style={styles.legendList}>
        {HEATMAP_LEGEND_ITEMS.map((item) => (
          <View key={item.key} style={styles.legendListRow}>
            {item.key === 'hatch' ? (
              <View style={[styles.hatchSwatch, styles.legendDot]}>
                {[0, 1, 2].map((i) => (
                  <View key={i} style={[styles.hatchLine, { left: i * 6 - 4 }]} />
                ))}
              </View>
            ) : (
              <View style={[styles.legendDot, { backgroundColor: LEGEND_SWATCH[item.key] }]} />
            )}
            <Text style={styles.legendListText}>
              <Text style={styles.legendListLabel}>{item.label}</Text> = {item.text}
            </Text>
          </View>
        ))}
      </View>
      <Text style={typo.body}>{heatmapCoverageNote(heatmap.modelName, heatmap.coveragePct, heatmap.partial)}</Text>

      {/* 보조 안내: 접어 둔다 */}
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: moreOpen }}
        onPress={() => setMoreOpen((o) => !o)}
        style={styles.guideToggle}>
        <Text style={styles.guideToggleText}>{moreOpen ? '색상 설명 접기' : '색상의 의미 자세히 보기'}</Text>
      </Pressable>
      {moreOpen && <Text style={typo.muted}>{HEATMAP_RELATIVE_NOTE}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.screen, gap: space.gap, paddingBottom: 40 },
  section: { gap: 12 },
  heatRow: { flexDirection: 'row', gap: 10 },
  heatCol: { flex: 1, gap: 6, minWidth: 0 },
  heatImage: { width: '100%', borderRadius: 8, backgroundColor: colors.track },
  heatCaption: { ...font.medium, fontSize: 12, lineHeight: 17, color: colors.textMuted, textAlign: 'center' },
  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end' },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 20 },
  legendTitle: { ...font.semibold, fontSize: 12, color: colors.textMuted },
  legendScale: { gap: 3 },
  legendRamp: { flexDirection: 'row', borderRadius: 3, overflow: 'hidden' },
  legendStep: { width: 16, height: 10 },
  legendLabels: { flexDirection: 'row', justifyContent: 'space-between' },
  legendText: { ...font.regular, fontSize: 12, color: colors.textMuted },
  legendList: { gap: 6 },
  legendListRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  legendDot: { width: 14, height: 14, borderRadius: 3 },
  legendListText: { ...font.regular, fontSize: 13, lineHeight: 19, color: colors.textMuted, flexShrink: 1 },
  legendListLabel: { ...font.semibold, color: colors.text },
  hatchSwatch: {
    width: 20,
    height: 14,
    borderRadius: 3,
    backgroundColor: '#B4B4B4',
    overflow: 'hidden',
  },
  hatchLine: {
    position: 'absolute',
    top: -4,
    width: 2,
    height: 24,
    backgroundColor: '#878787',
    transform: [{ rotate: '45deg' }],
  },
  guide: { gap: 8, paddingHorizontal: 4 },
  guideToggle: { minHeight: 40, justifyContent: 'center', alignSelf: 'flex-start' },
  guideToggleText: { ...font.semibold, fontSize: 14, color: colors.primary },
  savedNote: { backgroundColor: colors.primarySoft, borderRadius: 12, padding: 14, gap: 4 },
  savedLink: { minHeight: 40, justifyContent: 'center', alignSelf: 'flex-start' },
  savedText: { ...font.regular, fontSize: 13, lineHeight: 19, color: colors.navy },
});
