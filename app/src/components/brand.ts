// 브랜드 에셋: AI 탐정 로봇 (원본 SVG·생성 스크립트는 assets/brand/src).
// 캐릭터 이름·서비스 이름은 아직 정하지 않았다 — 여기서 이름을 붙이지 않는다.
// 앱 아이콘·시작 화면에 쓰고, 빈 화면·로딩·오류 화면에서 재사용할 수 있게 밝은/어두운 배경용을 둔다.
export const BRAND_IMAGES = {
  /** 앱 아이콘과 같은 둥근 사각형 마크 (헤더 로고, 기준 40pt) */
  mark: require('@/assets/brand/mark.png'),
  /** 밝은 배경용 캐릭터 (네이비 머리, 기준 120pt) */
  characterLight: require('@/assets/brand/character-light.png'),
  /** 어두운(네이비) 배경용 캐릭터 (밝은 머리, 기준 120pt) */
  characterDark: require('@/assets/brand/character-dark.png'),
  /** 시작 화면 전신 로봇 — 네이티브 스플래시(app.config.ts)와 같은 파일. 앱 아이콘은 얼굴 심볼(icon.png) 그대로 */
  splash: require('@/assets/brand/splash-fullbody.png'),
  /** 전신 캐릭터 (기준 160pt) — 빈 화면·로딩·오류에서 재사용 */
  fullBodyLight: require('@/assets/brand/fullbody-light.png'),
  fullBodyDark: require('@/assets/brand/fullbody-dark.png'),
};

/** 네이티브 스플래시와 같은 값이어야 전환할 때 로봇이 움직이지 않는다 (app.config.ts expo-splash-screen) */
export const SPLASH_BACKGROUND = '#202544';
export const SPLASH_IMAGE_WIDTH = 240;
