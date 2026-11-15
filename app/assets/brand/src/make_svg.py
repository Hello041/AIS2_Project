"""AI 탐정 로봇 캐릭터 SVG 원본 생성 (임시 도구, 저장소 밖).

usage: python make_svg.py <출력 폴더>
변형:
  character-on-dark.svg   네이비 배경용 (밝은 머리)  → 앱 아이콘, 스플래시
  character-on-light.svg  밝은 배경용 (네이비 머리)  → 앱 안 빈 화면·로딩·오류 등 재사용
  character-mono.svg      단색 실루엣 (Android 테마 아이콘)
  fullbody-on-dark.svg    전신 캐릭터, 네이비 배경용 → 시작 화면
  fullbody-on-light.svg   전신 캐릭터, 밝은 배경용 → 재사용
모두 1024×1024, 배경 투명. 캐릭터는 가운데 근처에 그리고, 정확한 배치는 compose.py가 알파 영역으로 맞춘다.
"""
import sys
from pathlib import Path

NAVY, INDIGO, BLUE, BG = "#202544", "#5267D8", "#8293EA", "#F4F5FA"

PALETTES = {
    # 머리, 얼굴창(visor), 눈, 귀·안테나, 렌즈 테두리, 렌즈 안, 손잡이
    "on-dark": dict(head="#F4F5FA", visor="#202544", eye="#8FA0F2", ear="#8293EA", ring="#5267D8",
                    lens="#8293EA", lens_op="0.28", handle="#8293EA", stem="#F4F5FA", hl="#FFFFFF"),
    "on-light": dict(head="#202544", visor="#11152E", eye="#8FA0F2", ear="#5267D8", ring="#5267D8",
                     lens="#8293EA", lens_op="0.30", handle="#5267D8", stem="#202544", hl="#FFFFFF"),
}


def character(p: dict) -> str:
    return f"""
  <!-- 안테나 -->
  <line x1="470" y1="262" x2="470" y2="196" stroke="{p['stem']}" stroke-width="26" stroke-linecap="round"/>
  <circle cx="470" cy="178" r="34" fill="{p['ear']}"/>
  <!-- 귀 -->
  <rect x="236" y="392" width="56" height="128" rx="28" fill="{p['ear']}"/>
  <rect x="648" y="392" width="56" height="128" rx="28" fill="{p['ear']}"/>
  <!-- 머리 -->
  <rect x="262" y="250" width="416" height="372" rx="150" fill="{p['head']}"/>
  <!-- 얼굴창 -->
  <rect x="314" y="342" width="312" height="184" rx="92" fill="{p['visor']}"/>
  <!-- 눈 (왼쪽은 보통, 오른쪽은 렌즈로 확대되어 크게) -->
  <circle cx="404" cy="434" r="30" fill="{p['eye']}"/>
  <!-- 돋보기: 오른쪽 눈 위 -->
  <circle cx="560" cy="440" r="124" fill="{p['lens']}" fill-opacity="{p['lens_op']}"/>
  <circle cx="560" cy="434" r="46" fill="{p['eye']}"/>
  <path d="M 492 392 A 82 82 0 0 1 560 358" fill="none" stroke="{p['hl']}" stroke-opacity="0.75" stroke-width="18" stroke-linecap="round"/>
  <circle cx="560" cy="440" r="124" fill="none" stroke="{p['ring']}" stroke-width="40"/>
  <line x1="652" y1="532" x2="778" y2="658" stroke="{p['handle']}" stroke-width="70" stroke-linecap="round"/>
"""


def mono() -> str:
    # 알파만 쓰이는 단색 아이콘: 머리에서 얼굴창을 뚫고, 눈·렌즈 테두리·손잡이를 채운다
    return """
  <defs>
    <mask id="face">
      <rect width="1024" height="1024" fill="white"/>
      <rect x="314" y="342" width="312" height="184" rx="92" fill="black"/>
      <circle cx="560" cy="440" r="144" fill="black"/>
    </mask>
  </defs>
  <line x1="470" y1="262" x2="470" y2="196" stroke="#fff" stroke-width="26" stroke-linecap="round"/>
  <circle cx="470" cy="178" r="34" fill="#fff"/>
  <rect x="236" y="392" width="56" height="128" rx="28" fill="#fff"/>
  <g mask="url(#face)"><rect x="262" y="250" width="416" height="372" rx="150" fill="#fff"/>
    <rect x="648" y="392" width="56" height="128" rx="28" fill="#fff"/></g>
  <circle cx="404" cy="434" r="30" fill="#fff"/>
  <circle cx="560" cy="434" r="46" fill="#fff"/>
  <circle cx="560" cy="440" r="124" fill="none" stroke="#fff" stroke-width="40"/>
  <line x1="652" y1="532" x2="778" y2="658" stroke="#fff" stroke-width="70" stroke-linecap="round"/>
"""



def full_body(p: dict) -> str:
    """전신 캐릭터 (시작 화면용). 얼굴은 아이콘과 같은 모양, 오른손에 돋보기를 들고 가슴에 스캔 표시."""
    return f"""
  <!-- 다리·발 -->
  <rect x="444" y="640" width="46" height="96" rx="23" fill="{p['ear']}"/>
  <rect x="534" y="640" width="46" height="96" rx="23" fill="{p['ear']}"/>
  <rect x="418" y="712" width="92" height="44" rx="22" fill="{p['head']}"/>
  <rect x="514" y="712" width="92" height="44" rx="22" fill="{p['head']}"/>
  <!-- 왼팔 (내림) -->
  <line x1="404" y1="470" x2="342" y2="590" stroke="{p['head']}" stroke-width="46" stroke-linecap="round"/>
  <circle cx="338" cy="600" r="28" fill="{p['ear']}"/>
  <!-- 몸통 -->
  <rect x="496" y="394" width="32" height="40" rx="10" fill="{p['ear']}"/>
  <rect x="388" y="424" width="248" height="236" rx="84" fill="{p['head']}"/>
  <!-- 가슴 스캔 창 -->
  <rect x="446" y="476" width="132" height="84" rx="26" fill="{p['visor']}"/>
  <line x1="472" y1="500" x2="552" y2="500" stroke="{p['eye']}" stroke-width="10" stroke-linecap="round"/>
  <line x1="472" y1="518" x2="532" y2="518" stroke="{p['eye']}" stroke-width="10" stroke-linecap="round" stroke-opacity="0.7"/>
  <line x1="472" y1="536" x2="544" y2="536" stroke="{p['eye']}" stroke-width="10" stroke-linecap="round" stroke-opacity="0.45"/>
  <!-- 오른팔 (들어 올려 돋보기) -->
  <line x1="620" y1="470" x2="708" y2="404" stroke="{p['head']}" stroke-width="46" stroke-linecap="round"/>
  <line x1="716" y1="398" x2="756" y2="338" stroke="{p['handle']}" stroke-width="34" stroke-linecap="round"/>
  <circle cx="714" cy="400" r="28" fill="{p['ear']}"/>
  <circle cx="800" cy="270" r="82" fill="{p['lens']}" fill-opacity="{p['lens_op']}"/>
  <path d="M 752 246 A 54 54 0 0 1 800 214" fill="none" stroke="{p['hl']}" stroke-opacity="0.75" stroke-width="14" stroke-linecap="round"/>
  <circle cx="800" cy="270" r="82" fill="none" stroke="{p['ring']}" stroke-width="28"/>
  <!-- 안테나 -->
  <line x1="512" y1="132" x2="512" y2="88" stroke="{p['stem']}" stroke-width="18" stroke-linecap="round"/>
  <circle cx="512" cy="74" r="24" fill="{p['ear']}"/>
  <!-- 귀 -->
  <rect x="340" y="214" width="40" height="92" rx="20" fill="{p['ear']}"/>
  <rect x="644" y="214" width="40" height="92" rx="20" fill="{p['ear']}"/>
  <!-- 머리 -->
  <rect x="362" y="128" width="300" height="270" rx="112" fill="{p['head']}"/>
  <!-- 얼굴창·눈 -->
  <rect x="400" y="196" width="224" height="132" rx="66" fill="{p['visor']}"/>
  <circle cx="470" cy="262" r="24" fill="{p['eye']}"/>
  <circle cx="554" cy="262" r="24" fill="{p['eye']}"/>
"""

def svg(body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">{body}</svg>\n'


out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
for name, p in PALETTES.items():
    (out / f"character-{name}.svg").write_text(svg(character(p)), encoding="utf-8")
(out / "character-mono.svg").write_text(svg(mono()), encoding="utf-8")
for name, p in PALETTES.items():
    (out / f"fullbody-{name}.svg").write_text(svg(full_body(p)), encoding="utf-8")
print("ok", sorted(x.name for x in out.glob("*.svg")))
