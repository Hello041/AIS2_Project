import { NativeTabs } from 'expo-router/native-tabs';

import { colors, font } from '@/components/theme';

// 하단 탭: 홈 / 내 기록 / 설정. 아이콘은 Expo Router 내장(iOS SF Symbols, Android Material Symbols) — 새 패키지 없음.
// 선택된 탭은 인디고, 나머지는 회색. 탭 막대 높이·Safe Area는 네이티브 탭이 처리한다.
export default function TabLayout() {
  return (
    <NativeTabs
      backgroundColor={colors.surface}
      tintColor={colors.primary}
      iconColor={{ default: colors.tabInactive, selected: colors.primary }}
      labelStyle={{
        default: { ...font.medium, fontSize: 11, color: colors.tabInactive },
        selected: { ...font.semibold, fontSize: 11, color: colors.primary },
      }}
      indicatorColor={colors.primarySoft}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Label>홈</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf={{ default: 'house', selected: 'house.fill' }} md="home" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="history">
        <NativeTabs.Trigger.Label>내 기록</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="clock.arrow.circlepath" md="history" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="settings">
        <NativeTabs.Trigger.Label>설정</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf={{ default: 'gearshape', selected: 'gearshape.fill' }} md="settings" />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
