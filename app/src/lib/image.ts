import * as ImagePicker from 'expo-image-picker';

import type { PickedImage } from './types';

export type PickResult =
  | { status: 'ok'; image: PickedImage }
  | { status: 'canceled' }
  | { status: 'error'; message: string };

export const MSG_UNSUPPORTED = '지원하지 않는 이미지입니다';
export const MSG_TOO_LARGE = '10MB 이하 이미지를 선택해 주세요';

/**
 * 갤러리에서 이미지 한 장을 고른다 (계획서 §2, §6).
 *
 * 형식·크기 검사는 여기서 하지 않는다. 피커의 mimeType·fileName·확장자는 실제 데이터와 다를 수 있어
 * (예: iOS에서 HEIC 데이터가 .jpg로 저장되는 경로), 분석 직전에 prepare.ts가 실제 바이트로 확인하고
 * 필요할 때만 JPEG로 변환한다.
 *
 * iOS는 preferredAssetRepresentationMode를 Current(원본 그대로)로 둔다.
 * Compatible이면 iOS가 HEIC를 한 번 JPEG로 재인코딩하고, 앱이 화소·용량 때문에 다시 인코딩하면 두 번 손실이 생긴다.
 * Current면 JPEG·PNG 원본은 바이트 그대로 오고, HEIC는 앱이 한 번만 변환한다.
 */
export async function pickImage(): Promise<PickResult> {
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ['images'],
    allowsEditing: false,
    quality: 1,
    preferredAssetRepresentationMode: ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Current,
  });
  if (result.canceled || !result.assets?.length) return { status: 'canceled' };

  const asset = result.assets[0];
  if (asset.type && asset.type !== 'image') return { status: 'error', message: MSG_UNSUPPORTED };

  return { status: 'ok', image: { uri: asset.uri, width: asset.width, height: asset.height } };
}
