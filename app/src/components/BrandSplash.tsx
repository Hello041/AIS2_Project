import { useEffect, useRef } from 'react';
import { Animated, Image, StyleSheet, Text, View } from 'react-native';

import { BRAND_IMAGES, SPLASH_BACKGROUND, SPLASH_IMAGE_WIDTH } from './brand';
import { font } from './theme';

/** 서비스명·문구가 나타나는 시간, 머무는 시간, 사라지는 시간 (전체 약 4초) */
const TEXT_IN_MS = 400;
const HOLD_MS = 3200;
const FADE_OUT_MS = 400;

/**
 * 앱 안 시작 화면: 네이티브 스플래시(네이비 + 로봇)와 같은 배경·같은 위치의 로봇 아래로 서비스명과 문구를 띄운 뒤
 * 사라진다. 아래에는 이미 홈 화면이 그려져 있어 자연스럽게 이어진다.
 * - 글꼴을 다 읽은 뒤에만 보여 준다(_layout.tsx) → 깨진 글자 없음.
 * - 타이머로만 끝나므로 어떤 경우에도 멈춰 있지 않는다. 화면 낭독기에는 서비스명만 읽힌다.
 */
export function BrandSplash({ onDone }: { onDone: () => void }) {
  const text = useRef(new Animated.Value(0)).current;
  const all = useRef(new Animated.Value(1)).current;
  const doneRef = useRef(onDone);
  useEffect(() => {
    doneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    const anim = Animated.sequence([
      Animated.timing(text, { toValue: 1, duration: TEXT_IN_MS, useNativeDriver: true }),
      Animated.delay(HOLD_MS),
      Animated.timing(all, { toValue: 0, duration: FADE_OUT_MS, useNativeDriver: true }),
    ]);
    anim.start(() => doneRef.current());
    // 애니메이션 콜백이 오지 않는 경우에도 반드시 닫는다
    const guard = setTimeout(() => doneRef.current(), TEXT_IN_MS + HOLD_MS + FADE_OUT_MS + 1500);
    return () => {
      anim.stop();
      clearTimeout(guard);
    };
  }, [text, all]);

  return (
    <Animated.View
      style={[StyleSheet.absoluteFill, styles.root, { opacity: all }]}
      accessible
      accessibilityLabel="TraceLens"
      pointerEvents="none">
      {/* 로봇: 화면 정중앙 (네이티브 스플래시와 같은 위치·크기) */}
      <Image source={BRAND_IMAGES.splash} style={styles.robot} resizeMode="contain" />
      <Animated.View
        style={[
          styles.textBox,
          { opacity: text, transform: [{ translateY: text.interpolate({ inputRange: [0, 1], outputRange: [8, 0] }) }] },
        ]}>
        <Text style={styles.name}>TraceLens</Text>
        <Text style={styles.tagline}>이미지의 흔적을 분석합니다.</Text>
      </Animated.View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  root: { backgroundColor: SPLASH_BACKGROUND, alignItems: 'center', justifyContent: 'center', zIndex: 100 },
  robot: { width: SPLASH_IMAGE_WIDTH, height: SPLASH_IMAGE_WIDTH },
  // 로봇 아래 (정중앙 기준으로 로봇 절반 + 여백만큼 내려서 로봇 위치는 바꾸지 않는다)
  textBox: {
    position: 'absolute',
    top: '50%',
    marginTop: SPLASH_IMAGE_WIDTH / 2 - 8, // 전신 로봇 그림 아래 여백만큼 당긴다
    left: 24,
    right: 24,
    alignItems: 'center',
    gap: 6,
  },
  name: { ...font.bold, fontSize: 24, lineHeight: 32, color: '#FFFFFF', letterSpacing: -0.3 },
  tagline: { ...font.regular, fontSize: 15, lineHeight: 22, color: '#B7C0EE' },
});

// 빈 화면 등에서 재사용할 수 있게 캐릭터만 보여 주는 작은 컴포넌트
export function BrandCharacter({ size = 96, onDark = false }: { size?: number; onDark?: boolean }) {
  return (
    <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <Image
        source={onDark ? BRAND_IMAGES.characterDark : BRAND_IMAGES.characterLight}
        style={{ width: size, height: size }}
        resizeMode="contain"
      />
    </View>
  );
}
