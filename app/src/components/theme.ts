import { StyleSheet, type TextStyle } from 'react-native';

// 디자인 시스템: 네이비 + 인디고 블루 + 화이트 (2026-11 UI 개선 요청).
// 판정 구간 색(BAND_COLOR, labels.ts)과 히트맵 색(파랑→노랑→빨강, 주목 강도)은 의미가 다르므로 여기 섞지 않는다.

export const colors = {
  navy: '#202544',
  primary: '#5267D8', // 인디고: 주요 버튼·선택된 탭·링크
  primaryPressed: '#4153BC',
  primaryDisabled: '#B7C0EE',
  primarySoft: '#EEF0FC', // 인디고 옅은 배경 (아이콘 칩 등)
  secondary: '#8293EA', // 보조 블루
  background: '#F4F5FA',
  surface: '#FFFFFF',
  text: '#202544',
  textMuted: '#747B91',
  textFaint: '#747B91', // 작은 글자도 흰 배경에서 읽히도록 보조 텍스트와 같은 값
  border: '#E6E8F0',
  track: '#EDEFF6',
  ok: '#2E9D6A', // 서버 연결 상태 점
  error: '#C2413E', // 오류 안내 (판정 '강함'과 다른 맥락)
  errorBg: '#FCEDED',
  tabInactive: '#9AA0B3',
};

/** Pretendard (assets/fonts, OFL). 굵기마다 파일이 달라 fontWeight 대신 fontFamily로 고른다 (Android 합성 굵기 방지). */
export const FONT_FILES = {
  'Pretendard-Regular': require('@/assets/fonts/Pretendard-Regular.otf'),
  'Pretendard-Medium': require('@/assets/fonts/Pretendard-Medium.otf'),
  'Pretendard-SemiBold': require('@/assets/fonts/Pretendard-SemiBold.otf'),
  'Pretendard-Bold': require('@/assets/fonts/Pretendard-Bold.otf'),
};

export const font = {
  regular: { fontFamily: 'Pretendard-Regular' },
  medium: { fontFamily: 'Pretendard-Medium' },
  semibold: { fontFamily: 'Pretendard-SemiBold' },
  bold: { fontFamily: 'Pretendard-Bold' },
} satisfies Record<string, TextStyle>;

/** 글자 크기·행간 (요청 표 기준) */
export const typo = StyleSheet.create({
  hero: { ...font.bold, fontSize: 27, lineHeight: 36, color: colors.text, letterSpacing: -0.4 },
  title: { ...font.bold, fontSize: 24, lineHeight: 32, color: colors.text, letterSpacing: -0.3 },
  cardTitle: { ...font.semibold, fontSize: 17, lineHeight: 24, color: colors.text },
  body: { ...font.regular, fontSize: 15, lineHeight: 23, color: colors.text },
  bodyStrong: { ...font.semibold, fontSize: 15, lineHeight: 23, color: colors.text },
  muted: { ...font.regular, fontSize: 14, lineHeight: 21, color: colors.textMuted },
  caption: { ...font.regular, fontSize: 13, lineHeight: 19, color: colors.textMuted },
  small: { ...font.medium, fontSize: 12, lineHeight: 17, color: colors.textMuted },
  button: { ...font.semibold, fontSize: 16 },
});

export const space = { screen: 20, gap: 16, card: 18 };
export const radius = { card: 16, button: 12, chip: 999 };
export const BUTTON_HEIGHT = 52;
export const TOUCH_MIN = 48; // 터치 영역 최소 높이

export const common = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.card,
    borderWidth: 1,
    borderColor: colors.border,
    padding: space.card,
    // 아주 옅은 그림자 하나만 (과한 그림자 금지)
    shadowColor: colors.navy,
    shadowOpacity: 0.05,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },
  screen: { flex: 1, backgroundColor: colors.background },
  divider: { height: 1, backgroundColor: colors.border },
});
