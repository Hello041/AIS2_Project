import Constants from 'expo-constants';
import { useRouter } from 'expo-router';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { confirmClearHistory } from '@/components/confirm';
import { colors, common, space, typo } from '@/components/theme';
import { ListRow, Logo, ScreenHeader, SectionLabel } from '@/components/ui';
import { useHistory } from '@/lib/historyStore';

// 설정: 개인정보 안내, 기록 관리, 이용 안내, 앱 정보. 안내 문구는 실제 구현과 같아야 한다
// (서버: 업로드를 메모리에서만 처리 / 앱: historyStore.ts가 판정 값만 이 기기 문서 폴더에 저장).
const PRIVACY_ITEMS = [
  '원본 이미지는 서버에 저장하지 않으며, 분석 후 폐기합니다.',
  '분석 기록은 이 기기 내부에만 저장됩니다.',
  '원본 이미지, 썸네일, GPS 및 EXIF 정보는 분석 기록에 저장하지 않습니다.',
  '모델 주목 영역(히트맵) 이미지도 기록에 저장하지 않습니다. 기록에는 분석 일시, 판정 결과, 직접 입력한 제목·메모만 남습니다.',
];

const GUIDE = [
  {
    title: 'AI 판별 결과는 참고 정보입니다',
    body: 'AI 탐지 모델은 100% 정확하지 않습니다. 실제 사진이 AI 생성으로, AI 생성 이미지가 실제 사진으로 잘못 판단될 수 있습니다. 압축·크기 변경·스크린샷 등으로 결과가 달라질 수도 있습니다.',
  },
  {
    title: "'판단하기 어려움'이 나오는 이유",
    body: '세 모델(Community Forensics, AIDE, B-Free)의 결과가 서로 엇갈리거나 점수가 경계 근처라 어느 한쪽이라고 보기 어려울 때 표시합니다. 잘못된 단정을 피하기 위해 확실하지 않으면 이 결과를 보여 줍니다. 분석 실패가 아닙니다.',
  },
  {
    title: '모델 주목 영역은 AI 생성의 증거가 아닙니다',
    body: '히트맵은 B-Free 모델이 이미지 안에서 상대적으로 더 주목한 영역을 색(파랑 → 노랑 → 빨강)으로 보여 줍니다. 모델의 주목 분포일 뿐 AI 생성 흔적의 위치를 찾아내는 기능이 아니므로, 빨간색이 AI 생성이 의심되는 영역이라는 뜻은 아닙니다. 색상은 이미지마다 개별적으로 정규화되어 이미지 간 비교에 쓸 수 없습니다.',
  },
];

export default function SettingsScreen() {
  const router = useRouter();
  const { records } = useHistory();
  const version = Constants.expoConfig?.version ?? '-';
  const appName = Constants.expoConfig?.name ?? 'TraceLens';

  return (
    <SafeAreaView style={common.screen} edges={['top', 'left', 'right']}>
      <ScrollView contentContainerStyle={styles.content} contentInsetAdjustmentBehavior="automatic">
        <ScreenHeader title="설정" />

        <View style={styles.group}>
          <SectionLabel>개인정보 보호</SectionLabel>
          <View style={[common.card, styles.textCard]}>
            {PRIVACY_ITEMS.map((t) => (
              <View key={t} style={styles.bulletRow}>
                <View style={styles.bulletDot} />
                <Text style={[typo.body, { flex: 1 }]}>{t}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={styles.group}>
          <SectionLabel>기록 관리</SectionLabel>
          <View style={[common.card, styles.listCard]}>
            <ListRow
              title="내 기록 확인"
              detail={records.length > 0 ? `저장된 기록 ${records.length}개` : '저장된 기록 없음'}
              onPress={() => router.navigate('/history')}
            />
            <View style={styles.rowDivider} />
            <ListRow
              title="전체 기록 삭제"
              danger
              accessibilityHint="확인 후 이 기기의 분석 기록을 모두 삭제합니다"
              onPress={() => {
                if (records.length > 0) confirmClearHistory(records.length);
              }}
              detail={records.length > 0 ? undefined : '삭제할 기록이 없습니다'}
            />
          </View>
        </View>

        <View style={styles.group}>
          <SectionLabel>이용 안내</SectionLabel>
          <View style={[common.card, styles.textCard]}>
            {GUIDE.map((g, i) => (
              <View key={g.title} style={[styles.guideItem, i > 0 && styles.guideDivider]}>
                <Text style={typo.bodyStrong}>{g.title}</Text>
                <Text style={typo.muted}>{g.body}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={styles.group}>
          <SectionLabel>앱 정보</SectionLabel>
          <View style={[common.card, styles.textCard]}>
            <View style={styles.appRow}>
              <Logo size={40} />
              <View style={{ flex: 1 }}>
                <Text style={typo.cardTitle}>{appName}</Text>
                <Text style={typo.caption}>버전 {version}</Text>
              </View>
            </View>
            <Text style={typo.muted}>
              이미지 한 장을 AI 탐지 모델 세 가지(Community Forensics, AIDE, B-Free)로 분석해 AI 생성 흔적을 &apos;약함 /
              판단하기 어려움 / 강함&apos;으로 보여 주는 참고용 서비스입니다 (18조 프로젝트).
            </Text>
            <Text style={typo.caption}>B-Free: Guillaro et al., CVPR 2025 (비영리 라이선스)</Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.screen, paddingTop: 12, paddingBottom: 32, gap: 24 },
  group: { gap: 10 },
  textCard: { gap: 12 },
  listCard: { padding: 0, overflow: 'hidden' },
  rowDivider: { height: 1, backgroundColor: colors.border, marginLeft: space.card },
  bulletRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  bulletDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.primary, marginTop: 9 },
  guideItem: { gap: 6 },
  guideDivider: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
  appRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
});
