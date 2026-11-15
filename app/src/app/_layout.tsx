import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';

import { BrandSplash } from '@/components/BrandSplash';
import { FONT_FILES, colors, font } from '@/components/theme';
import { loadHistory } from '@/lib/historyStore';

void SplashScreen.preventAutoHideAsync().catch(() => undefined);
SplashScreen.setOptions({ duration: 200, fade: true });

/** 글꼴 읽기가 끝나지 않아도 이 시간이 지나면 앱을 연다 (시작 화면에서 멈추지 않도록) */
const FONT_WAIT_MAX_MS = 4000;

// 시작 순서:
// 1) 네이티브 스플래시(설치 앱: 네이비 + 로봇, Expo Go: Expo Go 자체 화면)가 Pretendard를 읽는 동안 유지된다.
// 2) 글꼴 준비 → 네이티브 스플래시를 숨기고, 같은 배경·같은 위치의 로봇 아래로 서비스명이 나타나는 BrandSplash를 잠깐 보여 준다.
// 3) BrandSplash가 사라지면 이미 아래에 그려 둔 홈 화면이 보인다.
export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts(FONT_FILES);
  const [fontTimeout, setFontTimeout] = useState(false);
  const [introDone, setIntroDone] = useState(false);
  const ready = fontsLoaded || !!fontError || fontTimeout;

  useEffect(() => {
    void loadHistory(); // 홈의 최근 기록을 바로 보여 주도록 미리 읽는다
    const t = setTimeout(() => setFontTimeout(true), FONT_WAIT_MAX_MS);
    return () => clearTimeout(t);
  }, []);
  useEffect(() => {
    if (ready) void SplashScreen.hideAsync().catch(() => undefined);
  }, [ready]);
  const finishIntro = useCallback(() => setIntroDone(true), []);

  if (!ready) return null;

  return (
    <>
      <StatusBar style={introDone ? 'dark' : 'light'} />
      <Stack
        screenOptions={{
          headerTintColor: colors.text,
          headerTitleStyle: { ...font.semibold, fontSize: 17, color: colors.text },
          headerStyle: { backgroundColor: colors.background },
          contentStyle: { backgroundColor: colors.background },
          headerShadowVisible: false,
          headerBackButtonDisplayMode: 'minimal',
        }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="analyze" options={{ title: '분석 중' }} />
        <Stack.Screen name="result" options={{ title: '분석 결과' }} />
        <Stack.Screen name="record/[id]" options={{ title: '기록 상세' }} />
      </Stack>
      {!introDone && <BrandSplash onDone={finishIntro} />}
    </>
  );
}
