"""Portable PDF primitives shared by the mural report and review form."""

from collections import OrderedDict
from glob import glob
from io import BytesIO
from pathlib import Path
import os
import re

from PIL import Image, ImageCms, ImageOps
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont, TTFError
from reportlab.pdfgen.canvas import Canvas


W, H = A4
M = 43
BODY = W - 2 * M
INK, MUTED, RULE, PALE, TEAL, WARN = map(
    HexColor, ("#1E2825", "#53645E", "#CDD9D1", "#F1F5F1", "#205D52", "#9A4535")
)
GROUPS = {
    "loss": ("脱落迹象", "#992744"),
    "line": ("线痕", "#1A5A81"),
    "spot": ("斑点与斑块", "#825016"),
    "tonal": ("颜色或纹理变化", "#5B487E"),
    "other": ("其他现象", "#52615A"),
}
STATUS = "AI 草稿 · 待人工复核"
BASIS = {"高": "较清楚", "中": "有限", "低": "较弱"}
ASCII_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/+@%?&=#~-]*|[^\n]")
CLOSING = set("，。、！？）》】；：）〕〉”’］｝")
OPENING = set("（《【〔〈“‘［｛")


def setup_fonts():
    """Embed a local simplified-Chinese TrueType font when available."""
    configured = os.environ.get("MURAL_CJK_FONT")
    pairs = [
        (configured, os.environ.get("MURAL_CJK_BOLD_FONT", configured), 0),
        ("/System/Library/Fonts/STHeiti Light.ttc", "/System/Library/Fonts/STHeiti Medium.ttc", 0),
        ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc", 0),
        ("C:/Windows/Fonts/simhei.ttf", None, 0),
        ("/Library/Fonts/Arial Unicode.ttf", None, 0),
    ]
    for base in (Path(__file__).parent / "fonts", Path.home() / ".local/share/fonts", "/usr/share/fonts", "/usr/local/share/fonts"):
        for pattern in ("**/NotoSansSC*Regular*.ttf", "**/NotoSansSC*.ttf", "**/SourceHanSansSC*.ttf", "**/wqy-microhei.ttc", "**/wqy-zenhei.ttc"):
            for path in sorted(glob(str(Path(base) / pattern), recursive=True)):
                pairs.append((path, None, 0))
    for normal, bold, index in pairs:
        if not normal or not Path(normal).is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont("Mural CJK", normal, subfontIndex=index))
        except (OSError, ValueError, TTFError):
            continue
        if bold and normal != bold and Path(bold).is_file():
            try:
                pdfmetrics.registerFont(TTFont("Mural CJK Bold", bold, subfontIndex=index))
                return "Mural CJK", "Mural CJK Bold"
            except (OSError, ValueError, TTFError):
                pass
        return "Mural CJK", "Mural CJK"
    # Standard Chinese CID face for systems where an embeddable font is unavailable.
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light", "STSong-Light"


FONT, BOLD = setup_fonts()


def text(c, value, x, y, size=10, color=INK, font=FONT, align="left"):
    c.setFont(font, size)
    c.setFillColor(color)
    draw = {"left": c.drawString, "right": c.drawRightString, "center": c.drawCentredString}
    draw[align](x, y, str(value))


def wrapped(value, width, size, font=FONT):
    """Wrap Chinese text while keeping normal-length PDF labels and words intact."""
    rows = []
    for paragraph in str(value).split("\n"):
        if not paragraph:
            rows.append("")
            continue
        tokens = []
        for token in ASCII_WORD.findall(paragraph):
            if pdfmetrics.stringWidth(token, font, size) > width:
                tokens.extend(token)
            else:
                tokens.append(token)
        row = []
        used = 0.0
        for token in tokens:
            token_width = pdfmetrics.stringWidth(token, font, size)
            if row and used + token_width > width:
                carry = ""
                if len(row) > 1 and (token[0] in CLOSING or row[-1] in OPENING):
                    carry = row.pop()
                rows.append("".join(row).rstrip())
                row = [carry] if carry else []
                used = pdfmetrics.stringWidth(carry, font, size)
            if token.strip() or row:
                row.append(token)
                used += token_width
        if row:
            rows.append("".join(row).rstrip())
    return rows


def para(c, value, x, y, width=BODY, size=10.6, leading=16, color=INK, font=FONT):
    for line in wrapped(value, width, size, font):
        text(c, line, x, y, size, color, font)
        y -= leading
    return y


def rule(c, y, x=M, width=BODY):
    c.setStrokeColor(RULE)
    c.setLineWidth(0.65)
    c.line(x, y, x + width, y)


def header(c, kind, title, status=STATUS):
    text(c, kind, M, H - 38, 9, TEAL, BOLD)
    text(c, status, W - M, H - 38, 9, WARN, BOLD, "right")
    y = para(c, title, M, H - 70, BODY, 22, 26, INK, BOLD)
    rule(c, y + 8)
    return y - 14


def finish(c, short_title, date=""):
    rule(c, 36)
    footer = f"{short_title}   /   {date}" if date else short_title
    text(c, footer, M, 22, 8.5, MUTED)
    text(c, f"第 {c.getPageNumber()} 页", W - M, 22, 8.5, MUTED, FONT, "right")
    c.showPage()


def badge(c, label, x, y, color, size=8.5):
    width = pdfmetrics.stringWidth(str(label), BOLD, size) + 9
    c.setFillColor(color)
    c.roundRect(x, y - 3, width, size + 5, 2, stroke=0, fill=1)
    text(c, label, x + 4.5, y + 1, size, white, BOLD)
    return width


def group_key(region):
    group = region.get("map_group")
    if group in GROUPS:
        return group
    term = (region.get("diagnosis") or {}).get("primary") or region.get("type") or ""
    if any(word in term for word in ("裂", "擦", "划", "线痕", "线状")):
        return "line"
    if any(word in term for word in ("缺失", "脱落", "露底", "缺口")):
        return "loss"
    if any(word in term for word in ("斑", "附着", "沉积", "覆盖")):
        return "spot"
    if any(word in term for word in ("色", "纹理")):
        return "tonal"
    return "other"


def region_style(region):
    name, color = GROUPS[group_key(region)]
    return name, HexColor(color)


def photo_basis(region):
    level = (region.get("diagnosis") or {}).get("confidence") or region.get("confidence")
    return BASIS.get(level, "")


def coords(region):
    return "原图 x, y, w, h  /  " + ", ".join(map(str, region["bbox_xywh"])) + " px"


class Photo:
    def __init__(self, path):
        with Image.open(path) as source:
            im = ImageOps.exif_transpose(source)
            profile = source.info.get("icc_profile")
            if profile:
                try:
                    im = ImageCms.profileToProfile(
                        im, ImageCms.getOpenProfile(BytesIO(profile)),
                        ImageCms.createProfile("sRGB"), outputMode="RGB",
                    )
                except (OSError, ValueError, ImageCms.PyCMSError):
                    pass
            self.image = im.convert("RGB")
        self.size = self.image.size
        self._cache = OrderedDict()

    def image_data(self, box, px):
        key = (box, px)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        picture = self.image.crop(box) if box else self.image.copy()
        picture.thumbnail((px, px), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        picture.save(buffer, "JPEG", quality=91, subsampling=0)
        buffer.seek(0)
        item = ImageReader(buffer)
        self._cache[key] = item
        if len(self._cache) > 32:
            self._cache.popitem(last=False)
        return item

    def draw(self, c, box, x, top, width, height, px=1650, center=False):
        sx, sy, ex, ey = box or (0, 0, *self.size)
        scale = min(width / (ex - sx), height / (ey - sy))
        w, h = (ex - sx) * scale, (ey - sy) * scale
        if center:
            x += (width - w) / 2
        c.drawImage(self.image_data(box, px), x, top - h, w, h)
        return x, top, scale, sx, sy, w, h

    def crop_box(self, region):
        x, y, w, h = region["bbox_xywh"]
        im_w, im_h = self.size
        pad_x, pad_y = max(12, round(w * .23)), max(12, round(h * .23))
        return max(0, x - pad_x), max(0, y - pad_y), min(im_w, x + w + pad_x), min(im_h, y + h + pad_y)

    @staticmethod
    def point(mapping, sx, sy):
        x, top, scale, left, upper, _, _ = mapping
        return x + (sx - left) * scale, top - (sy - upper) * scale

    def outline(self, c, mapping, region, dashed=False):
        bx, by, bw, bh = region["bbox_xywh"]
        left, top = self.point(mapping, bx, by)
        scale = mapping[2]
        rw, rh = bw * scale, bh * scale
        _, color = region_style(region)
        c.saveState()
        if dashed:
            c.setDash(4, 2)
        c.setStrokeColor(white)
        c.setLineWidth(2.4)
        c.rect(left, top - rh, rw, rh, stroke=1, fill=0)
        c.setStrokeColor(color)
        c.setLineWidth(1.1)
        c.rect(left, top - rh, rw, rh, stroke=1, fill=0)
        c.restoreState()
        return left, top, rw, rh, color

    def mark_region(self, c, mapping, region):
        """Draw supplied native-pixel marks and return a usable label anchor."""
        marks = region.get("map_marks") or []
        if not marks:
            a, b, _, _, color = self.outline(c, mapping, region, dashed=True)
            return a, b, color
        _, color = region_style(region)
        anchors = []
        for mark in marks:
            kind = mark.get("kind")
            pts = [self.point(mapping, *point) for point in mark.get("points", [])]
            needed = {"point": 1, "line": 2, "polygon": 3}.get(kind)
            if not needed or len(pts) < needed:
                continue
            c.saveState()
            tentative = mark.get("tentative", False)
            if kind == "point":
                for x, y in pts:
                    c.setStrokeColor(white)
                    c.setLineWidth(1.1)
                    c.setFillColor(color)
                    c.circle(x, y, 3.0 if tentative else 2.8, stroke=1, fill=1)
                    if tentative:
                        c.setFillColor(white)
                        c.circle(x, y, 1.15, stroke=0, fill=1)
            else:
                path = c.beginPath()
                path.moveTo(*pts[0])
                for xy in pts[1:]:
                    path.lineTo(*xy)
                if kind == "polygon":
                    path.close()
                if tentative:
                    c.setDash(3, 2)
                c.setStrokeColor(white)
                c.setLineWidth(2.6)
                c.drawPath(path)
                c.setStrokeColor(color)
                c.setLineWidth(1.25)
                c.drawPath(path)
            c.restoreState()
            anchors.extend(pts)
        if not anchors:
            a, b, _, _, color = self.outline(c, mapping, region, dashed=True)
            return a, b, color
        a, b = max(anchors, key=lambda xy: xy[1])
        return a, b, color

    def location(self, c, region, x, top, w, h):
        mapping = self.draw(c, None, x, top, w, h, px=1050)
        gx, gy, _, _, color = self.outline(c, mapping, region, dashed=True)
        label = region["label"]
        badge_w = pdfmetrics.stringWidth(str(label), BOLD, 7) + 9
        badge(c, label, max(x, min(gx, x + mapping[5] - badge_w)), min(gy + 3, top - 9), color, 7)
        return mapping
