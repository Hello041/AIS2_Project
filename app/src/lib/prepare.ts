import { File, FileMode } from 'expo-file-system';
import { ImageManipulator, SaveFormat, type ImageRef } from 'expo-image-manipulator';

import {
  SERVER_MAX_BYTES,
  SERVER_MAX_PIXELS,
  extOf,
  maxSideForPixels,
  mimeOf,
  planUpload,
  serverOpensAsJpeg,
  sniffImage,
  type ImageInfo,
  type ReadAt,
} from './imageFormat';
import type { PickedImage } from './types';

/**
 * 업로드 전처리 (이미지 호환성).
 *
 * - 서버가 받는 정상 JPEG·PNG·WebP는 **원본 바이트 그대로** 보낸다 (재압축·축소 없음).
 * - Ultra HDR JPEG(유효한 MPF + 주 이미지 APP1의 ` hdrgm:Version="`)는 서버 Pillow 10.4가 JPEG로 받으므로 원본 그대로.
 * - 서버가 못 받는 형식(HEIC/HEIF, AVIF 등)·MPO(JPEG+보조 이미지)·2,500만 화소 초과·10MB 초과일 때만
 *   기기 디코더로 열어 **새 JPEG 파일**로 저장한다. 원본 파일은 읽기 전용으로만 연다.
 *
 * 변환하면 잃는 것 (재저장한 JPEG에는 남지 않는다):
 * - HDR 게인맵(UltraHDR·Apple HDR): 기본(SDR) 이미지만 남는다. MPO의 보조 이미지도 버린다.
 * - EXIF 전체(촬영 정보, GPS 포함)와 C2PA 출처 서명. → 변환본으로는 출처 확인을 할 수 없다.
 * - JPEG 재압축·축소로 인한 미세 신호 변화. AI 탐지 점수가 원본과 달라질 수 있다.
 * 방향(EXIF Orientation)은 디코더가 픽셀에 반영한 뒤 저장하므로, 변환본은 회전 정보 없이 바로 선 이미지다.
 */

/** 변환 JPEG 품질. 높은 값부터 써서 10MB 이하가 되는 첫 값을 고른다 (재압축 손실 최소화). */
const JPEG_QUALITIES = [0.95, 0.9, 0.85] as const;
/** 해상도를 모를 때 첫 디코딩의 긴 변 상한 (메모리 보호). 이후 화소 수를 확인해 한 번 더 줄인다 */
const UNKNOWN_SIZE_MAX_SIDE = 8192;

export type PrepareErrorKind = 'unsupported' | 'convert_failed' | 'resolution_too_high' | 'bytes_too_large';

export class PrepareError extends Error {
  readonly kind: PrepareErrorKind;
  constructor(kind: PrepareErrorKind, detail?: string) {
    super(detail ?? kind);
    this.name = 'PrepareError';
    this.kind = kind;
  }
}

export type PrepareStatus = 'checking' | 'converting';

export type PreparedUpload = {
  uri: string;
  /** 업로드 파트 파일명. 원본 파일명은 보내지 않는다 (개인정보) */
  name: string;
  mimeType: string;
  size: number;
  /** 원본을 그대로 보내면 false, 새 JPEG를 만들었으면 true */
  converted: boolean;
  /** 화소 제한 때문에 줄였는지 */
  resized: boolean;
  /** 변환한 이유 (planUpload가 정한 그대로). 원본 전송이면 빈 배열 */
  reasons: readonly ('format' | 'mpo' | 'pixels' | 'bytes')[];
  width?: number;
  height?: number;
  source: ImageInfo;
  /** 변환본(임시 파일)을 지운다. 원본에는 아무 일도 하지 않는다 */
  cleanup: () => void;
};

function readOnlyReader(file: File): { readAt: ReadAt; close: () => void } {
  const handle = file.open(FileMode.ReadOnly);
  return {
    readAt: async (offset, length) => {
      handle.offset = offset;
      return handle.readBytes(length);
    },
    close: () => handle.close(),
  };
}

async function inspect(uri: string): Promise<{ info: ImageInfo; size: number }> {
  const file = new File(uri);
  if (!file.exists) throw new PrepareError('unsupported', 'file not found');
  const reader = readOnlyReader(file);
  try {
    return { info: await sniffImage(reader.readAt), size: file.size };
  } finally {
    reader.close();
  }
}

function deleteQuietly(uri: string) {
  try {
    const f = new File(uri);
    if (f.exists) f.delete();
  } catch {
    // 캐시 정리 실패는 업로드에 영향 없음
  }
}

/** 기기 디코더로 열어(필요하면 축소하며) ImageRef를 만든다. 축소는 디코딩 단계에서 해 원본 크기 비트맵을 만들지 않는다. */
async function decode(
  uri: string,
  maxSide: number | undefined,
  sizeKnown: boolean,
): Promise<{ ref: ImageRef; resized: boolean }> {
  // 화소 초과면 계산한 긴 변 상한으로, 해상도를 모르면 메모리 보호용 상한으로, 제한 이내면 원래 해상도로 디코딩
  const bound = maxSide ?? (sizeKnown ? undefined : UNKNOWN_SIZE_MAX_SIDE);
  const ctx = ImageManipulator.manipulate(uri, bound !== undefined ? { maxWidth: bound, maxHeight: bound } : undefined);
  let ref: ImageRef;
  try {
    ref = await ctx.renderAsync();
  } finally {
    ctx.release();
  }
  let resized = maxSide !== undefined || (bound !== undefined && Math.max(ref.width, ref.height) >= bound);
  // 해상도를 미리 몰랐거나 반올림으로 넘친 경우, 실제 결과를 보고 한 번 더 줄인다.
  if (ref.width * ref.height > SERVER_MAX_PIXELS) {
    const side = maxSideForPixels(ref.width, ref.height);
    const ctx2 = ImageManipulator.manipulate(ref, { maxWidth: side, maxHeight: side });
    try {
      const ref2 = await ctx2.renderAsync();
      ref.release();
      ref = ref2;
      resized = true;
    } finally {
      ctx2.release();
    }
  }
  if (ref.width * ref.height > SERVER_MAX_PIXELS) {
    ref.release();
    throw new PrepareError('resolution_too_high');
  }
  return { ref, resized };
}

async function convertToJpeg(
  uri: string,
  maxSide: number | undefined,
  source: ImageInfo,
  sizeKnown: boolean,
  reasons: PreparedUpload['reasons'],
): Promise<PreparedUpload> {
  let decoded: { ref: ImageRef; resized: boolean };
  try {
    decoded = await decode(uri, maxSide, sizeKnown);
  } catch (e) {
    if (e instanceof PrepareError) throw e;
    throw new PrepareError('convert_failed', String(e));
  }
  const { ref, resized } = decoded;
  try {
    for (const quality of JPEG_QUALITIES) {
      let out: { uri: string; width: number; height: number };
      try {
        out = await ref.saveAsync({ format: SaveFormat.JPEG, compress: quality });
      } catch (e) {
        throw new PrepareError('convert_failed', String(e));
      }
      // 변환 결과도 실제 바이트로 확인한다. 원본 전송과 같은 규칙(serverOpensAsJpeg)으로 서버 Pillow가 JPEG로 열 것이
      // 확실할 때만 업로드한다. 예: Android 14+에서 게인맵이 남아 Ultra HDR JPEG로 저장되면 → 통과,
      // MPO이거나 MP 색인을 검증할 수 없으면 → 업로드하지 않음.
      const checked = await inspect(out.uri).catch(() => null);
      if (!checked || !serverOpensAsJpeg(checked.info)) {
        deleteQuietly(out.uri);
        throw new PrepareError('convert_failed', 'output is not a plain JPEG');
      }
      if (checked.size <= SERVER_MAX_BYTES) {
        return {
          uri: out.uri,
          name: 'image.jpg',
          mimeType: 'image/jpeg',
          size: checked.size,
          converted: true,
          resized,
          reasons,
          width: out.width,
          height: out.height,
          source,
          cleanup: () => deleteQuietly(out.uri),
        };
      }
      deleteQuietly(out.uri); // 10MB 초과 → 다음(낮은) 품질로
    }
    throw new PrepareError('bytes_too_large');
  } finally {
    ref.release();
  }
}

/** 고른 이미지를 서버가 받을 수 있는 형태로 준비한다. 원본 파일은 수정하지 않는다. */
export async function prepareImageForUpload(
  image: PickedImage,
  onStatus?: (s: PrepareStatus) => void,
): Promise<PreparedUpload> {
  onStatus?.('checking');
  let inspected: { info: ImageInfo; size: number };
  try {
    inspected = await inspect(image.uri);
  } catch (e) {
    if (e instanceof PrepareError) throw e;
    throw new PrepareError('unsupported', String(e));
  }
  const { info, size } = inspected;
  const plan = planUpload(info, size, { width: image.width, height: image.height });

  if (plan.action === 'reject') throw new PrepareError('unsupported');
  if (plan.action === 'original') {
    return {
      uri: image.uri,
      name: `image.${extOf(plan.format)}`,
      mimeType: mimeOf(plan.format),
      size,
      converted: false,
      resized: false,
      reasons: [],
      width: info.width,
      height: info.height,
      source: info,
      cleanup: () => {}, // 원본(피커가 준 파일)은 건드리지 않는다
    };
  }
  onStatus?.('converting');
  const sizeKnown = !!((info.width && info.height) || (image.width && image.height));
  return convertToJpeg(image.uri, plan.maxSide, info, sizeKnown, plan.reasons);
}
