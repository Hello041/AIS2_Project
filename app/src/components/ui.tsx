// 여러 화면이 함께 쓰는 작은 UI 조각 (디자인 통일용). 새 아이콘 패키지 없이 View로 그린다.
import type { ReactNode } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { BAND_COLOR, OVERALL_LABEL, OVERALL_NOTICE, SEGMENT_LABEL } from '@/lib/labels';
import type { ResultView } from '@/lib/resultView';
import type { ModelRow } from '@/lib/resultView';
import { BANDS, type Band } from '@/lib/types';

import { BRAND_IMAGES } from './brand';
import { TOUCH_MIN, colors, common, font, radius, space, typo } from './theme';

/** 서비스 로고: 앱 아이콘과 같은 AI 탐정 로봇 마크 (assets/brand/mark.png) */
export function Logo({ size = 40 }: { size?: number }) {
  return (
    <Image
      source={BRAND_IMAGES.mark}
      style={{ width: size, height: size }}
      accessibilityElementsHidden
      importantForAccessibility="no"
    />
  );
}

/** 오른쪽 화살표 (목록 항목 → 상세) */
export function Chevron({ color = colors.textMuted }: { color?: string }) {
  return (
    <View style={styles.chevronBox} accessibilityElementsHidden importantForAccessibility="no">
      <View style={[styles.chevron, { borderColor: color }]} />
    </View>
  );
}

/** 화면 상단 제목 + 보조 설명 */
export function ScreenHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <View style={styles.header}>
      <View style={{ flex: 1, gap: 4 }}>
        <Text style={typo.title} accessibilityRole="header">
          {title}
        </Text>
        {!!subtitle && <Text style={typo.muted}>{subtitle}</Text>}
      </View>
      {right}
    </View>
  );
}

/** 카드 묶음 위의 작은 제목 */
export function SectionLabel({ children, right }: { children: string; right?: ReactNode }) {
  return (
    <View style={styles.sectionLabelRow}>
      <Text style={styles.sectionLabel} accessibilityRole="header">
        {children}
      </Text>
      {right}
    </View>
  );
}

/** 종합 판정 배지 (색 + 글자) */
export function BandBadge({
  band,
  size = 'md',
  center = false,
}: {
  band: Band;
  size?: 'sm' | 'md' | 'lg';
  /** 가운데 정렬 카드 안에서 쓸 때 */
  center?: boolean;
}) {
  const tone = BAND_COLOR[band];
  const s = size === 'lg' ? styles.badgeLg : size === 'sm' ? styles.badgeSm : styles.badgeMd;
  const t = size === 'lg' ? styles.badgeTextLg : size === 'sm' ? styles.badgeTextSm : styles.badgeTextMd;
  return (
    <View style={[styles.badge, s, { backgroundColor: tone.bg }, center && { alignSelf: 'center' }]}>
      <View style={[styles.badgeDot, { backgroundColor: tone.dot }]} />
      <Text style={[t, { color: tone.fg }]}>{OVERALL_LABEL[band]}</Text>
    </View>
  );
}

/**
 * 종합 판정 카드 (결과 화면·기록 상세 공통): 가운데 정렬, 카드 전체 얇은 테두리.
 * 판정 의미·문구는 서버 overall 그대로 (overallView). 테두리는 판정 색을 옅게 써서 다른 카드와 통일감을 유지한다.
 */
export function OverallCard({ overall }: { overall: ResultView['overall'] }) {
  const tone = BAND_COLOR[overall.band];
  return (
    <View
      style={[common.card, styles.overall, { borderColor: tone.dot }]}
      accessible
      accessibilityLabel={`종합 판정: ${overall.label}. ${overall.description}${overall.note ? ` ${overall.note}` : ''}`}>
      <Text style={styles.overallCaption}>종합 판정</Text>
      <BandBadge band={overall.band} size="lg" center />
      {/* 가운데 정렬 문장은 한 글자만 다음 줄로 넘어가지 않도록 iOS에서 어절 단위로 줄바꿈 */}
      <Text style={styles.overallDescription} lineBreakStrategyIOS="hangul-word">
        {overall.description}
      </Text>
      {overall.note && (
        <Text style={[typo.muted, styles.center]} lineBreakStrategyIOS="hangul-word">
          {overall.note}
        </Text>
      )}
      <View style={styles.overallDivider} />
      <Text style={[typo.caption, styles.center]} lineBreakStrategyIOS="hangul-word">
        {OVERALL_NOTICE}
      </Text>
    </View>
  );
}

/** 모델별 판정 작은 칩: "B-Free 강함" */
export function ModelChip({ name, band }: { name: string; band: Band }) {
  const tone = BAND_COLOR[band];
  return (
    <View style={[styles.chip, { borderColor: tone.dot }]}>
      <Text style={styles.chipName}>{name}</Text>
      <Text style={[styles.chipBand, { color: tone.fg }]}>{SEGMENT_LABEL[band]}</Text>
    </View>
  );
}

/** 모델별 3칸 막대: 서버 band에 해당하는 칸 하나만 강조 (결과 화면·기록 상세 공통) */
export function ModelBars({ rows }: { rows: ModelRow[] }) {
  return (
    <View style={styles.models}>
      {rows.map((row) => (
        <ModelBar key={row.key} row={row} />
      ))}
    </View>
  );
}

function ModelBar({ row }: { row: ModelRow }) {
  const analyzed = row.band !== null;
  return (
    <View style={styles.modelBlock} accessible accessibilityLabel={`${row.name}: ${row.bandLabel}`}>
      <View style={styles.modelHeader}>
        <Text style={styles.modelName}>{row.name}</Text>
        {/* 색만으로 구분하지 않도록 선택된 구간을 글자로도 적는다 */}
        <Text style={[styles.modelBandText, { color: analyzed ? BAND_COLOR[row.band!].fg : colors.textMuted }]}>
          {row.bandLabel}
        </Text>
      </View>
      <View style={[styles.segments, !analyzed && { opacity: 0.8 }]}>
        {BANDS.map((b) => {
          const on = analyzed && b === row.band;
          return (
            <View
              key={b}
              style={[
                styles.segment,
                on && { backgroundColor: BAND_COLOR[b].bg, borderColor: BAND_COLOR[b].dot },
                !analyzed && styles.segmentMissing,
              ]}>
              <Text
                style={[
                  styles.segmentText,
                  on && { ...font.bold, color: BAND_COLOR[b].fg },
                  !analyzed && { color: colors.border },
                ]}>
                {SEGMENT_LABEL[b]}
              </Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

/** 설정 등의 목록 행: 왼쪽 글자, 오른쪽 화살표. danger면 빨간 글자 */
export function ListRow({
  title,
  detail,
  onPress,
  danger,
  accessibilityHint,
}: {
  title: string;
  detail?: string;
  onPress: () => void;
  danger?: boolean;
  accessibilityHint?: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityHint={accessibilityHint}
      onPress={onPress}
      style={({ pressed }) => [styles.listRow, pressed && { backgroundColor: colors.track }]}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[typo.bodyStrong, danger && { color: colors.error }]}>{title}</Text>
        {!!detail && <Text style={typo.caption}>{detail}</Text>}
      </View>
      {!danger && <Chevron />}
    </Pressable>
  );
}

/** 기록이 없을 때 */
export function EmptyState({ title, body }: { title: string; body?: string }) {
  return (
    <View style={[common.card, styles.empty]}>
      <View style={styles.emptyIcon} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
        <View style={styles.emptyLine} />
        <View style={[styles.emptyLine, { width: 18 }]} />
        <View style={[styles.emptyLine, { width: 22 }]} />
      </View>
      <Text style={[typo.bodyStrong, { textAlign: 'center' }]}>{title}</Text>
      {!!body && <Text style={[typo.caption, { textAlign: 'center' }]}>{body}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  overall: { alignItems: 'center', gap: 12, paddingVertical: 26, paddingHorizontal: 16, borderWidth: 1.5 },
  overallCaption: { ...font.bold, fontSize: 19, lineHeight: 26, color: colors.text, textAlign: 'center' },
  overallDescription: { ...font.semibold, fontSize: 17, lineHeight: 25, color: colors.text, textAlign: 'center' },
  overallDivider: { alignSelf: 'stretch', height: 1, backgroundColor: colors.border, marginVertical: 2 },
  center: { textAlign: 'center' },
  chevronBox: { width: 20, height: 20, alignItems: 'center', justifyContent: 'center' },
  chevron: {
    width: 9,
    height: 9,
    borderTopWidth: 2,
    borderRightWidth: 2,
    transform: [{ rotate: '45deg' }],
    marginLeft: -4,
  },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  sectionLabelRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: 24 },
  sectionLabel: { ...font.semibold, fontSize: 16, lineHeight: 22, color: colors.text },
  badge: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', borderRadius: radius.chip },
  badgeSm: { paddingVertical: 4, paddingHorizontal: 10, gap: 6 },
  badgeMd: { paddingVertical: 6, paddingHorizontal: 12, gap: 7 },
  badgeLg: { paddingVertical: 11, paddingHorizontal: 20, gap: 10 },
  badgeDot: { width: 8, height: 8, borderRadius: 4 },
  badgeTextSm: { ...font.semibold, fontSize: 13, lineHeight: 18 },
  badgeTextMd: { ...font.semibold, fontSize: 15, lineHeight: 20 },
  badgeTextLg: { ...font.bold, fontSize: 24, lineHeight: 32 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderWidth: 1,
    borderRadius: radius.chip,
    paddingVertical: 3,
    paddingHorizontal: 9,
    backgroundColor: colors.surface,
  },
  chipName: { ...font.medium, fontSize: 12, lineHeight: 17, color: colors.textMuted },
  chipBand: { ...font.semibold, fontSize: 12, lineHeight: 17 },
  models: { gap: 16 },
  modelBlock: { gap: 8 },
  modelHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  modelName: { ...font.semibold, fontSize: 16, lineHeight: 22, color: colors.text },
  modelBandText: { ...font.semibold, fontSize: 14, lineHeight: 20 },
  segments: { flexDirection: 'row', gap: 6 },
  segment: {
    flex: 1,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: 'transparent',
    backgroundColor: colors.track,
  },
  segmentMissing: { backgroundColor: colors.surface, borderColor: colors.border, borderStyle: 'dashed' },
  segmentText: { ...font.medium, fontSize: 14, color: colors.textMuted },
  listRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    minHeight: TOUCH_MIN + 8,
    paddingHorizontal: space.card,
    paddingVertical: 12,
  },
  empty: { alignItems: 'center', gap: 8, paddingVertical: 28 },
  emptyIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: colors.primarySoft,
    alignItems: 'flex-start',
    justifyContent: 'center',
    paddingLeft: 11,
    gap: 4,
    marginBottom: 4,
  },
  emptyLine: { width: 14, height: 3, borderRadius: 2, backgroundColor: colors.secondary },
});
