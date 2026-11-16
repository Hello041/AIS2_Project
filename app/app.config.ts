import type { ConfigContext, ExpoConfig } from 'expo/config';

// 서버 주소 (계획서 §6, CLAUDE.md): .env 또는 셸 환경 변수 API_BASE_URL
//   예) API_BASE_URL=http://192.168.0.10:8000   (같은 Wi-Fi, 노트북 IP)
//       API_BASE_URL=https://xxxx.ngrok-free.app
//       API_BASE_URL=mock                       (서버 없이 §5.4 예시 응답으로 화면 확인)
// 바꾼 뒤에는 `npx expo start`를 다시 실행한다.
export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: 'AI 이미지 판별',
  slug: 'ais2-app',
  version: '1.0.0',
  orientation: 'portrait',
  // 브랜드: AI 탐정 로봇 (assets/brand, 원본 SVG는 assets/brand/src)
  icon: './assets/brand/icon.png',
  scheme: 'ais2app',
  userInterfaceStyle: 'light',
  android: {
    adaptiveIcon: {
      backgroundColor: '#202544',
      foregroundImage: './assets/brand/android-foreground.png',
      backgroundImage: './assets/brand/android-background.png',
      monochromeImage: './assets/brand/android-monochrome.png',
    },
    predictiveBackGestureEnabled: false,
  },
  plugins: [
    'expo-router',
    [
      'expo-splash-screen',
      // 네이티브 시작 화면(설치 앱에서만 적용, Expo Go는 자체 화면): 네이비 + 전신 로봇 (앱 아이콘은 얼굴 심볼).
      // 서비스명·문구는 앱이 뜬 직후 BrandSplash(src/components/BrandSplash.tsx)가 같은 위치의 로봇 아래에 보여 준다.
      { backgroundColor: '#202544', image: './assets/brand/splash-fullbody.png', imageWidth: 240 },
    ],
  ],
  experiments: { typedRoutes: true, reactCompiler: true },
  extra: {
    apiBaseUrl: process.env.API_BASE_URL ?? '',
  },
});
