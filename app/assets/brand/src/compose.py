"""렌더한 캐릭터(2048px, 투명) → 앱 아이콘·스플래시·앱 안 에셋 PNG (임시 도구, 저장소 밖).

usage: python compose.py <렌더 폴더> <app/assets/brand 폴더> <미리보기 폴더>
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SRC, OUT, PREV = map(Path, sys.argv[1:4])
OUT.mkdir(parents=True, exist_ok=True)
PREV.mkdir(parents=True, exist_ok=True)
NAVY, NAVY_LIGHT, BG = (0x20, 0x25, 0x44), (0x2E, 0x36, 0x6A), (0xF4, 0xF5, 0xFA)


def load(name):
    im = Image.open(SRC / f"character-{name}.png").convert("RGBA")
    return im.crop(im.getchannel("A").getbbox())


def fit(im, box):
    """긴 변이 box가 되도록 (고품질 축소)"""
    s = box / max(im.size)
    return im.resize((round(im.width * s), round(im.height * s)), Image.Resampling.LANCZOS)


def place(canvas, im, cy_shift=0):
    x = (canvas.width - im.width) // 2
    y = (canvas.height - im.height) // 2 + cy_shift
    canvas.alpha_composite(im, (x, y))
    return canvas


def navy_bg(size):
    """네이비 + 가운데가 살짝 밝은 원형 그라데이션 (단색보다 입체감, 작은 크기에선 단색처럼 보임)"""
    bg = Image.new("RGBA", (size, size), NAVY + (255,))
    glow = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(glow)
    r = int(size * 0.42)
    d.ellipse((size // 2 - r, size // 2 - r - size // 16, size // 2 + r, size // 2 + r - size // 16), fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.12))
    light = Image.new("RGBA", (size, size), NAVY_LIGHT + (255,))
    return Image.composite(light, bg, glow)


dark, light, mono = load("on-dark"), load("on-light"), load("mono")
print("캐릭터 원본(2048 기준) 크기", dark.size)

# 1. 앱 아이콘 (iOS·기본): 1024 정사각형, 투명 없음, 글자 없음. 캐릭터 긴 변 = 64%
icon = place(navy_bg(1024), fit(dark, 655), cy_shift=8).convert("RGB")
icon.save(OUT / "icon.png", optimize=True)

# 2. Android 적응형 아이콘: 전경(투명) — 안전 영역(지름 66%) 안에 들어가도록 대각선 기준으로 줄인다
diag = (dark.width**2 + dark.height**2) ** 0.5
fg_scale = 0.66 * 1024 / diag
fg = fit(dark, round(max(dark.size) * fg_scale))
place(Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)), fg, cy_shift=6).save(OUT / "android-foreground.png", optimize=True)
navy_bg(1024).convert("RGB").save(OUT / "android-background.png", optimize=True)
monofg = fit(mono, round(max(mono.size) * fg_scale))
place(Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)), monofg, cy_shift=6).save(OUT / "android-monochrome.png", optimize=True)

# 3. 스플래시 이미지: 네이비 배경 위에 놓일 캐릭터 (투명, 정사각형 여백 포함)
splash = place(Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)), fit(dark, round(1024 * 0.94 * max(dark.size) / diag)))  # 대각선이 원(Android 12+ 원형 마스크) 안에 들어가게
splash.save(OUT / "splash-character.png", optimize=True)

# 4. 앱 안에서 재사용할 캐릭터 (기준 120pt, @2x·@3x) — 밝은 배경용 / 어두운 배경용
for name, im in [("character-light", light), ("character-dark", dark)]:
    for k in (1, 2, 3):
        side = 120 * k
        c = place(Image.new("RGBA", (side, side), (0, 0, 0, 0)), fit(im, round(side * 0.96)))
        c.save(OUT / (f"{name}.png" if k == 1 else f"{name}@{k}x.png"), optimize=True)

# 5. 로고 마크 (앱 안 헤더용): 앱 아이콘을 둥근 사각형으로 (기준 40pt, @2x·@3x)
for k in (1, 2, 3):
    side = 40 * k
    big = icon.resize((side * 4, side * 4), Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", big.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big.width - 1, big.height - 1), radius=int(big.width * 0.26), fill=255)
    big.putalpha(mask)
    big.resize((side, side), Image.Resampling.LANCZOS).save(OUT / (f"mark.png" if k == 1 else f"mark@{k}x.png"), optimize=True)

# ---- 미리보기 (저장소에 넣지 않음)
# 홈 화면 크기별 아이콘 (iOS 마스크 근사: 둥근 사각형)
sizes = [180, 120, 87, 60, 48, 40, 29]
sheet = Image.new("RGB", (sum(sizes) + 30 * len(sizes) + 30, 260), (236, 238, 245))
x = 30
for s in sizes:
    im = icon.resize((s, s), Image.Resampling.LANCZOS).convert("RGBA")
    m = Image.new("L", (s, s), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.225), fill=255)
    sheet.paste(im, (x, 40), m)
    ImageDraw.Draw(sheet).text((x, 40 + s + 8), f"{s}px", fill=(90, 90, 110))
    x += s + 30
sheet.save(PREV / "icon_sizes.png")

# Android 적응형: 원형 마스크 + 단색 테마
row = Image.new("RGB", (3 * 220 + 40, 240), (236, 238, 245))
fgimg = Image.open(OUT / "android-foreground.png")
bgimg = Image.open(OUT / "android-background.png").convert("RGBA")
for i, shape in enumerate(["circle", "squircle", "mono"]):
    comp = bgimg.copy()
    comp.alpha_composite(fgimg)
    if shape == "mono":
        comp = Image.new("RGBA", (1024, 1024), (40, 50, 70, 255))
        white = Image.new("RGBA", (1024, 1024), (200, 215, 255, 255))
        comp = Image.composite(white, comp, Image.open(OUT / "android-monochrome.png").getchannel("A"))
    comp = comp.resize((180, 180), Image.Resampling.LANCZOS)
    m = Image.new("L", (180, 180), 0)
    d = ImageDraw.Draw(m)
    (d.ellipse if shape != "squircle" else lambda b, fill: d.rounded_rectangle(b, radius=50, fill=fill))((0, 0, 179, 179), fill=255)
    row.paste(comp, (20 + i * 220, 30), m)
row.save(PREV / "android_adaptive.png")

# 밝은 배경 캐릭터
lp = Image.new("RGBA", (420, 200), BG + (255,))
lp.alpha_composite(Image.open(OUT / "character-light@3x.png").resize((160, 160), Image.Resampling.LANCZOS), (20, 20))
lp.alpha_composite(Image.open(OUT / "character-light.png"), (220, 40))
lp.convert("RGB").save(PREV / "character_light.png")
print("ok", sorted(p.name for p in OUT.glob("*.png")))

# ---- 전신 캐릭터 (시작 화면). 앱 아이콘은 위의 심볼 그대로 둔다.
def load_full(name):
    im = Image.open(SRC / f"fullbody-{name}.png").convert("RGBA")
    return im.crop(im.getchannel("A").getbbox())


full_dark, full_light = load_full("on-dark"), load_full("on-light")
fdiag = (full_dark.width**2 + full_dark.height**2) ** 0.5
# 네이티브 스플래시·앱 안 시작 화면 공용: 대각선이 원 안에 들어가게 (Android 12+ 원형 마스크)
splash_full = place(Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)), fit(full_dark, round(1024 * 0.94 * max(full_dark.size) / fdiag)))
splash_full.save(OUT / "splash-fullbody.png", optimize=True)
# 재사용: 전신 캐릭터 (기준 160pt, @2x·@3x)
for name, im in [("fullbody-light", full_light), ("fullbody-dark", full_dark)]:
    for k in (1, 2, 3):
        side = 160 * k
        c = place(Image.new("RGBA", (side, side), (0, 0, 0, 0)), fit(im, round(side * 0.96)))
        c.save(OUT / (f"{name}.png" if k == 1 else f"{name}@{k}x.png"), optimize=True)
print("fullbody ok")
