"""Build clean, shot-specific trading graphics for storyboards that define a scene type."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1080, 1920
INK = (10, 19, 34)
PANEL = (18, 32, 51)
PANEL_LIGHT = (25, 43, 64)
WHITE = (239, 245, 249)
MUTED = (143, 163, 181)
TEAL = (52, 222, 190)
RED = (255, 111, 119)
BLUE = (104, 168, 255)
GOLD = (255, 197, 107)

SCENES = {
    "market_noise": {
        "headline": "Noise isn't a strategy.",
        "subhead": "A clear process beats chasing every move.",
        "label": "START WITH A PLAN",
    },
    "missed_move": {
        "headline": "The market keeps moving.",
        "subhead": "You don't need to react to every tick.",
        "label": "MARKET MOVEMENT · ILLUSTRATIVE",
    },
    "zoom_out": {
        "headline": "Zoom out. See more.",
        "subhead": "Bring multiple perspectives into the same decision.",
        "label": "A BROADER MARKET VIEW",
    },
    "signal_flow": {
        "headline": "Read the context.",
        "subhead": "Market data, sentiment and options flow—in one view.",
        "label": "SIGNAL INPUTS · ILLUSTRATIVE",
    },
    "diversify": {
        "headline": "Look beyond one ticker.",
        "subhead": "Explore signals across a wider watchlist.",
        "label": "A WIDER WATCHLIST",
    },
    "risk_check": {
        "headline": "Check before you act.",
        "subhead": "Review the setup, signal and risk for yourself.",
        "label": "A MORE DELIBERATE CHECKLIST",
    },
    "call_to_action": {
        "headline": "A clearer market view.",
        "subhead": "Explore market signals with CrowdWisdomTrading.",
        "label": "CROWDWISDOMTRADING",
    },
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"]
        if bold else
        ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"]
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _fit_font(draw: ImageDraw.ImageDraw, text: str, size: int, max_width: int) -> ImageFont.FreeTypeFont:
    while size > 24:
        font = _font(size, bold=True)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
        size -= 2
    return _font(size, bold=True)


def _background() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        blend = y / HEIGHT
        color = tuple(int(INK[i] * (1 - blend) + (16, 39, 57)[i] * blend) for i in range(3))
        draw.line((0, y, WIDTH, y), fill=color)

    grid = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid)
    for x in range(44, WIDTH, 72):
        grid_draw.line((x, 120, x, 1770), fill=(119, 157, 182, 13), width=1)
    for y in range(160, 1770, 72):
        grid_draw.line((38, y, WIDTH - 38, y), fill=(119, 157, 182, 13), width=1)
    return Image.alpha_composite(image.convert("RGBA"), grid).convert("RGB")


def _card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill=PANEL) -> None:
    draw.rounded_rectangle(box, radius=28, fill=fill, outline=(47, 69, 91), width=2)


def _line_chart(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], seed: int, color=TEAL) -> None:
    left, top, right, bottom = box
    for step in range(1, 5):
        y = top + (bottom - top) * step // 5
        draw.line((left, y, right, y), fill=(49, 68, 87), width=2)

    values = (
        [0.77, 0.69, 0.74, 0.53, 0.62, 0.42, 0.57, 0.36, 0.46, 0.25, 0.34, 0.18, 0.28, 0.12]
        if seed % 2 else
        [0.78, 0.67, 0.73, 0.58, 0.64, 0.47, 0.55, 0.40, 0.45, 0.31, 0.37, 0.21, 0.27, 0.14]
    )
    points = [
        (left + index * (right - left) // (len(values) - 1), top + int(value * (bottom - top)))
        for index, value in enumerate(values)
    ]
    draw.line(points, fill=color, width=8, joint="curve")
    x, y = points[-1]
    draw.ellipse((x - 13, y - 13, x + 13, y + 13), fill=color)
    draw.ellipse((x - 24, y - 24, x + 24, y + 24), outline=(*color, 100), width=3)


def _candlesticks(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    for step in range(1, 5):
        y = top + (bottom - top) * step // 5
        draw.line((left, y, right, y), fill=(49, 68, 87), width=2)
    values = [
        (0.71, 0.58, False), (0.62, 0.43, True), (0.47, 0.62, False),
        (0.63, 0.48, False), (0.54, 0.35, True), (0.41, 0.53, False),
        (0.56, 0.40, True), (0.44, 0.60, False), (0.61, 0.45, False),
        (0.52, 0.29, True), (0.37, 0.51, False), (0.54, 0.34, True),
        (0.43, 0.24, True), (0.32, 0.44, False), (0.46, 0.27, True),
        (0.35, 0.17, True),
    ]
    spacing = (right - left) / (len(values) + 1)
    for index, (start, end, up) in enumerate(values, start=1):
        x = int(left + spacing * index)
        color = TEAL if up else RED
        y1, y2 = top + int(start * (bottom - top)), top + int(end * (bottom - top))
        draw.line((x, y1 - 18, x, y2 + 18), fill=color, width=3)
        draw.rounded_rectangle((x - 10, min(y1, y2), x + 10, max(y1, y2)), radius=4, fill=color)


def _draw_scene(draw: ImageDraw.ImageDraw, scene_type: str) -> None:
    if scene_type == "market_noise":
        _card(draw, (64, 610, 1016, 1390))
        draw.text((106, 652), "INTRADAY PRICE ACTION", font=_font(25, True), fill=MUTED)
        _candlesticks(draw, (112, 760, 968, 1240))
        _card(draw, (126, 1274, 954, 1350), PANEL_LIGHT)
        draw.ellipse((158, 1296, 190, 1328), fill=RED)
        draw.text((212, 1292), "Noise pulls you in every direction", font=_font(27), fill=WHITE)
    elif scene_type == "missed_move":
        _card(draw, (64, 610, 1016, 1390))
        draw.text((106, 652), "PRICE MOVEMENT · ILLUSTRATIVE", font=_font(25, True), fill=MUTED)
        _line_chart(draw, (112, 790, 968, 1200), 1, BLUE)
        _card(draw, (126, 1240, 954, 1350), PANEL_LIGHT)
        draw.ellipse((158, 1279, 190, 1311), fill=GOLD)
        draw.text((212, 1274), "Build a routine. Avoid chasing.", font=_font(30, True), fill=WHITE)
    elif scene_type == "zoom_out":
        _card(draw, (64, 610, 1016, 1390))
        draw.text((106, 652), "THREE USEFUL PERSPECTIVES", font=_font(25, True), fill=MUTED)
        labels = [("PRICE", BLUE), ("SENTIMENT", TEAL), ("OPTIONS FLOW", GOLD)]
        for index, (label, color) in enumerate(labels):
            top = 758 + index * 174
            _card(draw, (110, top, 970, top + 126), PANEL_LIGHT)
            draw.rounded_rectangle((138, top + 28, 150, top + 98), radius=6, fill=color)
            draw.text((182, top + 40), label, font=_font(32, True), fill=WHITE)
            draw.text((786, top + 39), f"0{index + 1}", font=_font(30, True), fill=color)
        draw.text((142, 1310), "More context. Your decision.", font=_font(31, True), fill=TEAL)
    elif scene_type == "signal_flow":
        _card(draw, (64, 610, 1016, 1390))
        draw.text((106, 652), "SIGNAL INPUTS · ILLUSTRATIVE", font=_font(25, True), fill=MUTED)
        inputs = [("MARKET", BLUE), ("SENTIMENT", TEAL), ("OPTIONS FLOW", GOLD)]
        for index, (label, color) in enumerate(inputs):
            x = 112 + index * 292
            _card(draw, (x, 786, x + 260, 964), PANEL_LIGHT)
            draw.ellipse((x + 104, 817, x + 156, 869), fill=color)
            draw.text((x + 20, 892), label, font=_font(21, True), fill=WHITE)
            if index < 2:
                draw.line((x + 266, 875, x + 286, 875), fill=MUTED, width=4)
        _line_chart(draw, (128, 1082, 952, 1270), 4, TEAL)
        draw.text((130, 1300), "Observe  →  compare  →  decide", font=_font(30, True), fill=WHITE)
    elif scene_type == "diversify":
        _card(draw, (64, 610, 1016, 1390))
        draw.text((106, 652), "WATCHLIST OVERVIEW", font=_font(25, True), fill=MUTED)
        rows = [("LARGE-CAP", BLUE), ("INDEX", TEAL), ("OPTIONS", GOLD), ("SECTORS", RED)]
        for index, (label, color) in enumerate(rows):
            top = 750 + index * 142
            _card(draw, (110, top, 970, top + 108), PANEL_LIGHT)
            draw.ellipse((144, top + 34, 184, top + 74), fill=color)
            draw.text((212, top + 31), label, font=_font(29, True), fill=WHITE)
            for bar in range(4):
                x = 590 + bar * 76
                draw.rounded_rectangle((x, top + 37, x + 44, top + 71), radius=8,
                                       fill=color if bar <= index else (51, 68, 87))
        draw.text((138, 1330), "Explore the market beyond one name.", font=_font(27, True), fill=TEAL)
    elif scene_type == "risk_check":
        _card(draw, (64, 610, 1016, 1390))
        draw.text((106, 652), "BEFORE YOU PLACE A TRADE", font=_font(25, True), fill=MUTED)
        checks = [
            ("01", "SETUP", "What is the opportunity?"),
            ("02", "SIGNAL", "What supports the idea?"),
            ("03", "RISK", "What could go wrong?"),
        ]
        for index, (number, label, prompt) in enumerate(checks):
            top = 760 + index * 182
            _card(draw, (110, top, 970, top + 140), PANEL_LIGHT)
            draw.text((146, top + 22), number, font=_font(24, True), fill=TEAL)
            draw.text((216, top + 20), label, font=_font(31, True), fill=WHITE)
            draw.text((216, top + 74), prompt, font=_font(23), fill=MUTED)
            draw.ellipse((882, top + 51, 916, top + 85), outline=TEAL, width=3)
        draw.text((140, 1330), "Signals inform. You decide.", font=_font(29, True), fill=GOLD)
    elif scene_type == "call_to_action":
        _card(draw, (64, 610, 1016, 1390))
        draw.ellipse((365, 710, 715, 1060), fill=(23, 58, 71), outline=TEAL, width=5)
        draw.line((448, 884, 520, 957), fill=TEAL, width=22)
        draw.line((520, 957, 645, 797), fill=TEAL, width=22)
        draw.text((145, 1110), "MARKET CLARITY STARTS WITH CONTEXT", font=_font(27, True), fill=MUTED)
        draw.rounded_rectangle((150, 1190, 930, 1308), radius=28, fill=TEAL)
        draw.text((540, 1249), "EXPLORE SIGNALS", font=_font(34, True), fill=INK, anchor="mm")
    else:
        raise ValueError(f"Unknown storyboard scene type: {scene_type}")


def render_scene(scene_type: str, output_path: Path, scene_number: int, scene_count: int) -> Path:
    """Render a legible, scene-matched vertical graphic without relying on image-generation text."""
    try:
        scene = SCENES[scene_type]
    except KeyError as exc:
        raise ValueError(f"Unknown storyboard scene type: {scene_type}") from exc

    image = _background()
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((64, 66, 520, 136), radius=32, fill=(20, 46, 60))
    draw.ellipse((89, 91, 109, 111), fill=TEAL)
    draw.text((130, 83), "CWT  /  MARKET INTELLIGENCE", font=_font(23, True), fill=WHITE)
    draw.text((68, 230), scene["label"], font=_font(24, True), fill=TEAL)
    draw.text((64, 300), scene["headline"], font=_fit_font(draw, scene["headline"], 68, WIDTH - 136), fill=WHITE)
    draw.text((68, 405), scene["subhead"], font=_fit_font(draw, scene["subhead"], 27, WIDTH - 136), fill=MUTED)

    _draw_scene(draw, scene_type)

    draw.text((68, 1620), "INFORMATIONAL ONLY  ·  TRADING INVOLVES RISK", font=_font(20, True), fill=MUTED)
    draw.rounded_rectangle((68, 1742, WIDTH - 68, 1750), radius=4, fill=(51, 71, 89))
    progress = int((WIDTH - 136) * scene_number / max(scene_count, 1))
    draw.rounded_rectangle((68, 1742, 68 + progress, 1750), radius=4, fill=TEAL)
    draw.text((68, 1785), "CROWDWISDOMTRADING", font=_font(21, True), fill=WHITE)
    draw.text((WIDTH - 68, 1785), f"{scene_number:02d}  /  {scene_count:02d}",
              font=_font(21, True), fill=MUTED, anchor="ra")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=95)
    return output_path
