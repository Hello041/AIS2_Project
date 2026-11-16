// 실제 이미지 형식 판정과 업로드 전처리 계획 (순수 함수, Expo 의존성 없음 → Node에서 단위 검증 가능).
//
// 확장자·MIME은 실제 데이터와 다를 수 있다(예: iOS에서 HEIC 데이터가 .jpg로 저장되는 경로가 있음).
// 그래서 파일 앞부분의 시그니처와 헤더만 읽어 형식·해상도를 판정한다. 파일 전체를 읽지 않는다.

/** 서버(inference/main.py) 제한과 같게 유지한다. */
export const SERVER_MAX_BYTES = 10 * 1024 * 1024;
export const SERVER_MAX_PIXELS = 25_000_000;

export type RealFormat = 'jpeg' | 'png' | 'webp' | 'heif' | 'avif' | 'gif' | 'bmp' | 'tiff' | 'unknown';

export type ImageInfo = {
  format: RealFormat;
  /** 헤더에서 읽은 저장 해상도(EXIF 회전 전). 못 읽으면 undefined */
  width?: number;
  height?: number;
  /**
   * JPEG 주 이미지 헤더의 MPF(APP2 'MPF\0') 정보. 서버 Pillow처럼 **마지막** MPF 세그먼트 기준.
   * 세그먼트가 없으면 undefined. valid=false면 색인을 끝까지 검증하지 못한 것(이미지 수만 읽혔을 수도 있음).
   */
  mpf?: { images?: number; valid: boolean };
  /** 주 이미지 헤더의 APP1 중 하나에 Pillow 10.4가 Ultra HDR로 보는 문자열(` hdrgm:Version="`)이 있는지 */
  ultraHdrMarker?: boolean;
  /** HDR 게인맵 흔적('hdrgm', Apple 'HDRGainMap' 등)을 헤더에서 봤는지 (참고용, 판정에는 쓰지 않음) */
  gainMapHint?: boolean;
  /** HEIF 계열 ftyp 브랜드 (참고용) */
  brand?: string;
};

/** 파일의 [offset, offset+length) 바이트를 읽는 함수. 파일 끝이면 더 짧게 돌려준다. */
export type ReadAt = (offset: number, length: number) => Promise<Uint8Array>;

const SERVER_FORMATS: readonly RealFormat[] = ['jpeg', 'png', 'webp'];
/** 기기 디코더(iOS ImageIO, Android)로 열어 JPEG로 바꿔 볼 수 있는 형식 */
const CONVERTIBLE_FORMATS: readonly RealFormat[] = ['heif', 'avif', 'gif', 'bmp', 'tiff'];

const HEIF_BRANDS = ['heic', 'heix', 'hevc', 'hevx', 'heim', 'heis', 'mif1', 'msf1', 'mif2', 'miaf'];
const AVIF_BRANDS = ['avif', 'avis'];

const ascii = (b: Uint8Array, start: number, end: number) =>
  String.fromCharCode(...Array.from(b.subarray(start, end)));
const u16be = (b: Uint8Array, i: number) => (b[i] << 8) | b[i + 1];
const u16le = (b: Uint8Array, i: number) => b[i] | (b[i + 1] << 8);
const u24le = (b: Uint8Array, i: number) => b[i] | (b[i + 1] << 8) | (b[i + 2] << 16);
const u32be = (b: Uint8Array, i: number) => ((b[i] << 24) >>> 0) + ((b[i + 1] << 16) | (b[i + 2] << 8) | b[i + 3]);

function includesAscii(b: Uint8Array, needle: string): boolean {
  const n = needle.length;
  outer: for (let i = 0; i + n <= b.length; i++) {
    for (let j = 0; j < n; j++) if (b[i + j] !== needle.charCodeAt(j)) continue outer;
    return true;
  }
  return false;
}

/** 시그니처로 형식을 판정하고, 형식별 헤더에서 해상도 등을 읽는다. */
export async function sniffImage(readAt: ReadAt): Promise<ImageInfo> {
  const head = await readAt(0, 64);
  if (head.length >= 3 && head[0] === 0xff && head[1] === 0xd8 && head[2] === 0xff) {
    return readJpeg(readAt);
  }
  if (head.length >= 24 && ascii(head, 0, 8) === '\x89PNG\r\n\x1a\n' && ascii(head, 12, 16) === 'IHDR') {
    return { format: 'png', width: u32be(head, 16), height: u32be(head, 20) };
  }
  if (head.length >= 16 && ascii(head, 0, 4) === 'RIFF' && ascii(head, 8, 12) === 'WEBP') {
    return readWebp(head);
  }
  if (head.length >= 12 && ascii(head, 4, 8) === 'ftyp') {
    const size = Math.min(u32be(head, 0), head.length);
    const brands = [ascii(head, 8, 12)];
    for (let i = 16; i + 4 <= size; i += 4) brands.push(ascii(head, i, i + 4));
    if (brands.some((x) => AVIF_BRANDS.includes(x))) return { format: 'avif', brand: brands[0] };
    if (brands.some((x) => HEIF_BRANDS.includes(x))) return { format: 'heif', brand: brands[0] };
    return { format: 'unknown', brand: brands[0] };
  }
  if (head.length >= 6 && (ascii(head, 0, 6) === 'GIF87a' || ascii(head, 0, 6) === 'GIF89a')) {
    return { format: 'gif', width: u16le(head, 6), height: u16le(head, 8) };
  }
  if (head.length >= 2 && ascii(head, 0, 2) === 'BM') return { format: 'bmp' };
  if (head.length >= 4 && (ascii(head, 0, 4) === 'II*\x00' || ascii(head, 0, 4) === 'MM\x00*')) {
    return { format: 'tiff' };
  }
  return { format: 'unknown' };
}

function readWebp(h: Uint8Array): ImageInfo {
  const chunk = ascii(h, 12, 16);
  if (chunk === 'VP8 ' && h.length >= 30) {
    return { format: 'webp', width: u16le(h, 26) & 0x3fff, height: u16le(h, 28) & 0x3fff };
  }
  if (chunk === 'VP8L' && h.length >= 25) {
    const bits = h[21] | (h[22] << 8) | (h[23] << 16) | (h[24] << 24);
    return { format: 'webp', width: (bits & 0x3fff) + 1, height: ((bits >>> 14) & 0x3fff) + 1 };
  }
  if (chunk === 'VP8X' && h.length >= 30) {
    return { format: 'webp', width: u24le(h, 24) + 1, height: u24le(h, 27) + 1 };
  }
  return { format: 'webp' };
}

/** JPEG 마커를 차례로 건너뛰며 SOF(해상도)와 APP2 MPF(이미지 수)를 찾는다. 세그먼트 머리만 읽는다. */
async function readJpeg(readAt: ReadAt): Promise<ImageInfo> {
  const info: ImageInfo = { format: 'jpeg' };
  let pos = 2;
  let reachedScan = false;
  for (let guard = 0; guard < 512; guard++) {
    const m = await readAt(pos, 4);
    if (m.length < 4 || m[0] !== 0xff) break;
    const marker = m[1];
    if (marker === 0xff) {
      pos += 1; // 채움 바이트
      continue;
    }
    if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) {
      pos += 2;
      continue;
    }
    if (marker === 0xda) {
      reachedScan = true; // SOS: 헤더 끝, 이후는 압축 데이터
      break;
    }
    if (marker === 0xd9) break; // 데이터 없이 EOI
    const len = u16be(m, 2);
    if (len < 2) break;
    const isSof = marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc;
    if (isSof && info.width === undefined) {
      const sof = await readAt(pos + 4, 5);
      if (sof.length === 5) {
        info.height = u16be(sof, 1);
        info.width = u16be(sof, 3);
      }
    } else if (marker === 0xe2 || marker === 0xe1) {
      // APP2 'MPF\0' → MP 색인, APP1 → Ultra HDR 표시. 세그먼트는 최대 64KB.
      const seg = await readAt(pos + 4, len - 2);
      if (marker === 0xe2 && seg.length >= 4 && ascii(seg, 0, 4) === 'MPF\x00') {
        info.mpf = parseMpf(seg.subarray(4)); // Pillow처럼 뒤에 나온 MPF가 앞의 것을 덮는다
      }
      if (marker === 0xe1 && includesAscii(seg, PILLOW_ULTRA_HDR_NEEDLE)) info.ultraHdrMarker = true;
      if (includesAscii(seg, 'hdrgm') || includesAscii(seg, 'HDRGainMap') || includesAscii(seg, 'hdrgainmap')) {
        info.gainMapHint = true;
      }
    }
    pos += 2 + len;
  }
  if (!reachedScan) {
    // 헤더가 SOS 전에 끝났다 = 잘렸거나 손상. 해상도를 비워 planUpload가 거부하게 한다.
    delete info.width;
    delete info.height;
  }
  return info;
}

/**
 * 서버 Pillow 10.4.0(JpegImagePlugin.jpeg_factory)이 MPF 이미지 수가 2 이상이어도 MPO가 아닌 JPEG로 여는 조건.
 * 주 이미지의 APP1 세그먼트 중 하나에 이 바이트열(앞 공백 포함)이 있으면 "Ultra HDR images are not yet supported"로
 * JPEG 처리한다. 서버 Pillow 버전이 바뀌면 이 규칙도 다시 확인해야 한다.
 */
export const PILLOW_ULTRA_HDR_NEEDLE = ' hdrgm:Version="';

/**
 * MPF(TIFF 구조) 색인을 Pillow `_getmp()`가 요구하는 만큼 검증한다:
 * IFD를 읽을 수 있고, NumberOfImages(0xB001, LONG)와 MPEntry(0xB002, 16바이트×이미지 수 이상)가 있고,
 * 각 항목의 ImageDataFormat이 JPEG(0)일 것. 하나라도 어긋나면 valid=false
 * (Pillow는 이 경우 JPEG로 열거나(SyntaxError) 아예 못 연다(struct.error → 400)).
 */
function parseMpf(t: Uint8Array): { images?: number; valid: boolean } {
  if (t.length < 8) return { valid: false };
  const le = t[0] === 0x49 && t[1] === 0x49;
  if (!le && !(t[0] === 0x4d && t[1] === 0x4d)) return { valid: false };
  const r16 = (i: number) => (le ? t[i] | (t[i + 1] << 8) : (t[i] << 8) | t[i + 1]);
  const r32 = (i: number) =>
    le ? (t[i] | (t[i + 1] << 8) | (t[i + 2] << 16) | (t[i + 3] << 24)) >>> 0 : u32be(t, i);
  if (r16(2) !== 42) return { valid: false };
  const ifd = r32(4);
  if (ifd + 2 > t.length) return { valid: false };
  const entries = r16(ifd);
  let images: number | undefined;
  let mpEntry: { offset: number; length: number } | undefined;
  for (let k = 0; k < entries; k++) {
    const e = ifd + 2 + k * 12;
    if (e + 12 > t.length) return { images, valid: false };
    const tag = r16(e);
    const type = r16(e + 2);
    const count = r32(e + 4);
    if (tag === 0xb001) {
      if (type !== 4 || count !== 1) return { valid: false }; // LONG 1개
      images = r32(e + 8);
    } else if (tag === 0xb002) {
      if (type !== 7) return { images, valid: false }; // UNDEFINED 바이트열
      mpEntry = { offset: count <= 4 ? e + 8 : r32(e + 8), length: count };
    }
  }
  if (images === undefined || !mpEntry) return { images, valid: false };
  if (mpEntry.length < images * 16 || mpEntry.offset + images * 16 > t.length) return { images, valid: false };
  for (let i = 0; i < images; i++) {
    const attr = r32(mpEntry.offset + i * 16);
    if (((attr >>> 24) & 7) !== 0) return { images, valid: false }; // ImageDataFormat ≠ JPEG
  }
  return { images, valid: true };
}

export type JpegKind = 'plain' | 'ultra_hdr' | 'mpo' | 'unverified';

/**
 * 서버 Pillow 10.4.0이 이 JPEG를 어떻게 열지 앱에서 재현한다.
 * - plain: MPF 없음, 또는 유효한 MPF에 이미지 1장 이하 → JPEG
 * - ultra_hdr: 유효한 MPF에 이미지 2장 이상 + 주 이미지 APP1에 ` hdrgm:Version="` → JPEG (원본 그대로 가능)
 * - mpo: 유효한 MPF에 이미지 2장 이상, Ultra HDR 표시 없음 → MPO (서버 400)
 * - unverified: MPF가 있는데 색인을 끝까지 검증하지 못함 → 서버 결과를 확신할 수 없음
 */
export function jpegKind(info: ImageInfo): JpegKind {
  if (!info.mpf) return 'plain';
  if (!info.mpf.valid || info.mpf.images === undefined) return 'unverified';
  if (info.mpf.images <= 1) return 'plain';
  return info.ultraHdrMarker ? 'ultra_hdr' : 'mpo';
}

/** 서버 Pillow가 확실히 JPEG(MPO 아님)로 여는 JPEG인지. 원본 전송 여부와 변환 결과 검사에 같이 쓴다. */
export function serverOpensAsJpeg(info: ImageInfo): boolean {
  if (info.format !== 'jpeg' || !info.width || !info.height) return false;
  const kind = jpegKind(info);
  return kind === 'plain' || kind === 'ultra_hdr';
}

// ---------------------------------------------------------------- 전처리 계획

export type UploadPlan =
  | { action: 'original'; format: 'jpeg' | 'png' | 'webp' }
  | {
      action: 'convert';
      reasons: ('format' | 'mpo' | 'pixels' | 'bytes')[];
      /** 디코딩할 때 쓸 긴 변 상한(정사각 상한이라 EXIF 회전과 무관). 없으면 원래 해상도 */
      maxSide?: number;
    }
  | { action: 'reject'; reason: 'unsupported' };

/**
 * 원칙: 서버가 받는 정상 이미지는 원본 그대로. 서버가 못 받는 형식·MPO·화소 초과·용량 초과일 때만 변환.
 * width/height는 헤더 값이 우선이고, 없으면 피커 값(fallback)을 쓴다.
 */
export function planUpload(
  info: ImageInfo,
  fileBytes: number,
  fallback?: { width?: number; height?: number },
): UploadPlan {
  const w = info.width || fallback?.width || 0;
  const h = info.height || fallback?.height || 0;
  const pixels = w > 0 && h > 0 ? w * h : undefined;

  const reasons: ('format' | 'mpo' | 'pixels' | 'bytes')[] = [];
  if (SERVER_FORMATS.includes(info.format)) {
    // 시그니처는 맞는데 헤더에서 해상도를 못 읽었다 = 잘렸거나 손상된 파일. 지원 형식으로 간주하지 않는다.
    if (!info.width || !info.height) return { action: 'reject', reason: 'unsupported' };
    // MPO(서버 400)이거나 MP 색인을 검증하지 못한 JPEG만 변환한다.
    // Ultra HDR(유효한 MPF + 주 이미지 APP1의 ` hdrgm:Version="`)은 서버 Pillow 10.4가 JPEG로 받으므로 원본 그대로.
    if (info.format === 'jpeg' && !serverOpensAsJpeg(info)) reasons.push('mpo');
  } else if (CONVERTIBLE_FORMATS.includes(info.format)) {
    reasons.push('format');
  } else {
    return { action: 'reject', reason: 'unsupported' }; // 형식을 모르면 지원된다고 가정하지 않는다
  }
  if (pixels !== undefined && pixels > SERVER_MAX_PIXELS) reasons.push('pixels');
  if (fileBytes > SERVER_MAX_BYTES) reasons.push('bytes');

  if (reasons.length === 0) {
    return { action: 'original', format: info.format as 'jpeg' | 'png' | 'webp' };
  }
  const maxSide = pixels !== undefined && pixels > SERVER_MAX_PIXELS ? maxSideForPixels(w, h) : undefined;
  return { action: 'convert', reasons, maxSide };
}

/**
 * w×h를 비율 그대로 줄여 화소 수가 SERVER_MAX_PIXELS 이하가 되는 가장 큰 '긴 변' 길이.
 * 디코더는 긴 변을 이 값에 맞추고 짧은 변을 반올림하므로, 반올림까지 감안해 확인한다.
 */
export function maxSideForPixels(w: number, h: number, limit = SERVER_MAX_PIXELS): number {
  const long = Math.max(w, h);
  const short = Math.min(w, h);
  let side = Math.floor(Math.sqrt(limit * (long / short)));
  while (side > 1 && side * Math.max(1, Math.round((short * side) / long)) > limit) side--;
  return Math.min(side, long);
}

export function mimeOf(format: 'jpeg' | 'png' | 'webp'): string {
  return `image/${format}`;
}

export function extOf(format: 'jpeg' | 'png' | 'webp'): string {
  return format === 'jpeg' ? 'jpg' : format;
}
