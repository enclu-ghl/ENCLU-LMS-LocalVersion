"""라이트/다크 팔레트.

카드마다 지정된 뱃지 색(badge_bg)은 라이트 배경을 전제로 만든 연한 파스텔이라
다크 모드에서 그대로 쓰면 카드가 흰 판때기처럼 떠 보인다. 그래서 다크에서는
badge_color를 카드 배경에 살짝 섞어 어두운 톤으로 계산해서 쓴다.
"""

LIGHT = {
    "BG":       "#F7F7F5",
    "BG_CARD":  "#FFFFFF",
    "BG_HDR":   "#F0EFFD",
    "ACCENT":   "#534AB7",
    "ACCENT_L": "#EEEDFE",
    "ACCENT_H": "#3C3489",
    "ACCENT_FG": "#C5C1F5",
    "TEXT":     "#1A1A1A",
    "TEXT_SUB": "#888780",
    "BORDER":   "#E0DFF9",
    "DIVIDER":  "#E8E8E6",
    "DISABLED": "#BDBDBD",
    "DISABLED_H": "#9E9E9E",
    "OK":       "#2E7D32",
    "WARN":     "#B71C1C",
}

DARK = {
    "BG":       "#1B1B1F",
    "BG_CARD":  "#26262B",
    "BG_HDR":   "#222229",
    "ACCENT":   "#6C61D6",
    "ACCENT_L": "#2E2A47",
    "ACCENT_H": "#8A7FEC",
    "ACCENT_FG": "#BDB6F2",
    "TEXT":     "#EDEDF0",
    "TEXT_SUB": "#9A9AA3",
    "BORDER":   "#3A3A45",
    "DIVIDER":  "#33333B",
    "DISABLED": "#4A4A55",
    "DISABLED_H": "#5A5A66",
    "OK":       "#7BC67E",
    "WARN":     "#EF8A85",
}

THEMES = {"light": LIGHT, "dark": DARK}


def get(name: str) -> dict:
    return THEMES.get(name, LIGHT)


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(round(c)))) for c in rgb))


def blend(color_a: str, color_b: str, t: float) -> str:
    """color_a 를 color_b 쪽으로 t(0~1)만큼 섞는다."""
    a, b = _hex_to_rgb(color_a), _hex_to_rgb(color_b)
    return _rgb_to_hex(tuple(x + (y - x) * t for x, y in zip(a, b)))


def badge_colors(info: dict, palette: dict, theme_name: str):
    """카드 아이콘 영역의 (배경색, 전경색)을 테마에 맞게 계산."""
    if theme_name != "dark":
        return info["badge_bg"], info["badge_color"]
    # 다크: 카드 배경에 강조색을 22% 섞어 은은한 틴트를 만들고, 글자는 밝게 올린다.
    bg = blend(palette["BG_CARD"], info["badge_color"], 0.22)
    fg = blend(info["badge_color"], "#FFFFFF", 0.45)
    return bg, fg
