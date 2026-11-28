"""Render a reusable, paginated mural condition and conservation report."""

import argparse
from collections import Counter
from datetime import date
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caselog
from pdf_style import (
    A4, BODY, BOLD, FONT, GROUPS, H, INK, M, MUTED, TEAL, W, Canvas, HexColor,
    Photo, badge, coords, finish, group_key, header, para, photo_basis, pdfmetrics,
    region_style, rule, text, wrapped,
)


SHORT_TITLE = "病害识别与保护建议"
BOTTOM = 59
SECTORS = ("左上", "上中", "右上", "左中", "中央", "右中", "左下", "下中", "右下")
METHOD = (
    ("坐标", "以基准照片左上角为原点，向右为 x、向下为 y。x、y、w、h 的单位为像素。"),
    ("点线面", "圆点定位独立斑点，线条描记可追踪走向，闭合轮廓描记可辨面积边缘。虚线或空心点提示需复核的边界。"),
    ("定位框", "矩形虚框圈定局部复查范围，可纳入多处同类斑点和正常画面，也可能重叠。框的面积不作为病害面积。"),
    ("照片依据", "较清楚、有限、较弱表示影像对该条判读的支持程度。材料成分、层位与变化情况由相应资料或现场核查确定。"),
    ("核查顺序", "核查优先取决于部位、潜在影响和补证价值。现场处置紧迫度由文物保护人员现场评估。"),
)


def display_copy(value):
    value = str(value)
    for level, label in (("高", "较清楚"), ("中", "有限"), ("低", "较弱")):
        value = re.sub(f"(?:判读)?置信度[为：: ]*{level}(?:等)?", f"照片依据{label}", value)
    return value.replace("判读置信度", "照片依据").replace("置信度", "照片依据")


def preview(value, limit=96):
    value = " ".join(display_copy(value).split())
    return value if len(value) <= limit else value[:limit - 1].rstrip() + "…"


def label_of(region):
    diagnosis = region.get("diagnosis") or {}
    return region.get("map_title") or diagnosis.get("primary") or region.get("type") or region.get("phenomenon") or "影像异常"


def sentence(value):
    value = display_copy(value).strip()
    if value and value[-1] not in "。！？：":
        return value + "。"
    return value


def reference_key(suggestion):
    return f'suggestion:{suggestion["no"]}'


def region_key(region):
    return f'region:{region["label"]}'


class Report:
    def __init__(self, path, title):
        self.canvas = Canvas(str(path), pagesize=A4, pageCompression=1)
        self.canvas.setTitle(title)
        self.canvas.setSubject("基准照片病害判读与保护建议")
        self.started = False
        self.date = date.today().isoformat()

    def start(self, kind, title, key=None):
        if self.started:
            finish(self.canvas, SHORT_TITLE, self.date)
        self.kind = kind
        self.title = title
        self.y = header(self.canvas, kind, preview(title))
        self.started = True
        if key:
            self.canvas.bookmarkPage(key)
            self.canvas.addOutlineEntry(title, key, level=0)

    def ensure(self, height):
        if self.y - height < BOTTOM:
            kind, title = self.kind, self.title
            if not title.endswith("（续）"):
                title += "（续）"
            self.start(kind, title)

    def lines(self, value, *, x=M, width=BODY, size=10.6, lead=16, color=INK, font=FONT, linked=None, url=None):
        for line in wrapped(display_copy(value), width, size, font):
            self.ensure(lead)
            text(self.canvas, line, x, self.y, size, color, font)
            if linked or url:
                right = x + pdfmetrics.stringWidth(line, font, size)
                rectangle = (x, self.y - 4, right, self.y + size)
                if linked:
                    self.canvas.linkRect("", linked, rectangle, thickness=0)
                elif url.startswith(("https://", "http://")):
                    self.canvas.linkURL(url, rectangle, thickness=0)
            self.y -= lead

    def subheading(self, title):
        self.ensure(48)
        self.y -= 7
        self.lines(title, size=13, lead=20, color=TEAL, font=BOLD)

    def field(self, label, value, *, x=M, width=BODY, label_width=73, size=10.6, leading=15.5, linked=None, url=None):
        if not value:
            return
        self.ensure(leading + 5)
        text(self.canvas, label, x, self.y, size, TEAL, BOLD)
        self.lines(value, x=x + label_width, width=width - label_width, size=size, lead=leading, linked=linked, url=url)
        self.y -= 4.5

    def close(self):
        pages = self.canvas.getPageNumber()
        finish(self.canvas, SHORT_TITLE, self.date)
        self.canvas.save()
        return pages


def tile_box(photo, number):
    width, height = photo.size
    col, row = (number - 1) % 3, (number - 1) // 3
    return col * width // 3, row * height // 3, (col + 1) * width // 3, (row + 1) * height // 3


def tile_number(photo, region):
    existing = region.get("map_sector")
    if existing in {f"T{i}" for i in range(1, 10)}:
        return int(existing[1:])
    x, y, w, h = region["bbox_xywh"]
    width, height = photo.size
    return min(2, int((x + w / 2) * 3 / width)) + min(2, int((y + h / 2) * 3 / height)) * 3 + 1


def sector_name(index):
    return f"T{index}  {SECTORS[index - 1]}"


def draw_cover(doc, title, photo, regions, suggestions, meta, review, advice, sectors):
    c = doc.canvas
    doc.start(SHORT_TITLE, title, "overview")
    image_w, image_h = photo.size
    doc.lines(f"{image_w} × {image_h} px   /   {len(regions)} 个观察编号   /   {len(suggestions)} 条保护建议",
              size=11, color=TEAL, font=BOLD)
    top = doc.y - 6
    mp = photo.draw(c, None, M, top, 315, 386, 1700, center=True)
    for region in sorted(regions, key=lambda r: -(r["bbox_xywh"][2] * r["bbox_xywh"][3])):
        photo.mark_region(c, mp, region)
    for number in sectors:
        x0, y0, x1, y1 = tile_box(photo, number)
        left, upper = photo.point(mp, x0, y0)
        right, lower = photo.point(mp, x1, y1)
        if mp[5] > 90 and mp[6] > 70:
            badge(c, f"T{number}", left + 4, upper - 14, TEAL, 7.5)
        c.linkRect("", f"T{number}", (left, lower, right, upper), thickness=0)
    sx = M + 333
    sw = W - M - sx
    side_y = top - 12
    text(c, "现象分布", sx, side_y, 13, TEAL, BOLD)
    side_y -= 22
    counts = Counter(group_key(g) for g in regions)
    for key, count in counts.items():
        name, color = GROUPS[key]
        c.setFillColor(HexColor(color))
        c.rect(sx, side_y - 1, 9, 6, stroke=0, fill=1)
        side_y = para(c, f"{name}  {count}", sx + 15, side_y, sw - 15, 10, 12) - 7
    if not counts:
        side_y = para(c, "本次未保留观察编号。可评范围及限制见下一页。", sx, side_y, sw, 10, 15)
    priority = sum((g.get("diagnosis") or {}).get("priority") == "优先" for g in regions)
    if priority:
        side_y = para(c, f"建议优先核查 {priority} 处。", sx, side_y - 5, sw, 10.2, 15)
    if counts:
        side_y = para(c, "点击对应分区查看放大图。编号用于定位和复核。", sx, side_y - 8, sw, 10, 15, MUTED)
        side_y = para(c, "虚框圈定复查范围。点、线和闭合轮廓标示已补记的局部位置、走向或边缘。", sx, side_y - 6, sw, 9.5, 14, MUTED)
    doc.y = min(top - mp[6] - 25, side_y - 8)
    doc.field("图像", meta.get("image_name") or "", size=9.6)
    doc.field("来源", meta.get("image_source") or "未提供", size=9.6)
    models = [review.get("reviewer_model"), advice.get("advisor_model")]
    models = "、".join(dict.fromkeys(m for m in models if m))
    doc.field("判读与建议", models, size=9.6)


def draw_scope(doc, review, sectors):
    doc.start("影像检查", "评估范围与读图方法", "scope")
    doc.lines(review.get("overall_observation") or "未提供评估范围和成像限制。")
    doc.y -= 12
    for label, value in METHOD:
        doc.field(label, value)
    if sectors:
        doc.subheading("分区导航")
        draw_link_grid(doc, [(f"{sector_name(number)}　{len(regions)} 处", f"T{number}")
                             for number, regions in sectors.items()])
    priorities = [region for groups in sectors.values() for region in groups
                  if (region.get("diagnosis") or {}).get("priority") == "优先"]
    if priorities:
        doc.subheading("优先核查区域")
        draw_link_grid(doc, [(f'{g["label"]}  {preview(label_of(g), 60)}', region_key(g)) for g in priorities])


def draw_link_grid(doc, entries):
    width = (BODY - 16) / 2
    for start in range(0, len(entries), 2):
        row = [(wrapped(value, width, 9.8), target) for value, target in entries[start:start + 2]]
        height = 13 * max(len(lines) for lines, _ in row) + 4
        doc.ensure(height)
        for index, (lines, target) in enumerate(row):
            x = M + index * (width + 16)
            for pos, line in enumerate(lines):
                text(doc.canvas, line, x, doc.y - pos * 13, 9.8, TEAL)
            doc.canvas.linkRect("", target, (x, doc.y - height + 4, x + width, doc.y + 11), thickness=0)
        doc.y -= height


def place_badges(c, photo, mapping, regions):
    occupied = []
    mx, top, _, _, _, width, height = mapping
    for region in sorted(regions, key=lambda r: -(r["bbox_xywh"][2] * r["bbox_xywh"][3])):
        x, y, color = photo.mark_region(c, mapping, region)
        occupied.append((region, x, y, color))
    drawn = []
    for region, x, y, color in occupied:
        label = region["label"]
        badge_w = pdfmetrics.stringWidth(str(label), BOLD, 8) + 9
        ax = max(mx, min(x, mx + width - badge_w))
        ay = max(top - height + 4, min(y + 5, top - 11))
        choices = [(ax + ox, ay + oy) for ox, oy in (
            (0, 0), (0, -13), (0, 13), (0, -26), (0, 26),
            (26, 0), (-26, 0), (30, -13), (-30, -13),
        )]
        for bx, by in choices:
            if bx < mx or bx + badge_w > mx + width + .1 or by > top - 10 or by < top - height + 3:
                continue
            overlaps = any(bx < ex + 2 and bx + badge_w + 2 > sx and abs(by - sy) < 12 for sx, sy, ex in drawn)
            if overlaps:
                continue
            if (abs(bx - ax) + abs(by - ay)) >= 12:
                c.saveState()
                c.setLineWidth(.7)
                c.setStrokeColor(color)
                c.line(x, y, max(bx, min(x, bx + badge_w)), by - 3)
                c.restoreState()
            badge(c, label, bx, by, color, 8)
            c.linkRect("", region_key(region), (bx, by - 3, bx + badge_w, by + 9), thickness=0)
            drawn.append((bx, by, bx + badge_w))
            break


def draw_tile(doc, photo, number, regions):
    c = doc.canvas
    doc.start("分区图谱", sector_name(number), f"T{number}")
    iw, ih = photo.size
    x, y, x1, y1 = tile_box(photo, number)
    for g in regions:
        bx, by, bw, bh = g["bbox_xywh"]
        x, y, x1, y1 = min(x, bx), min(y, by), max(x1, bx + bw), max(y1, by + bh)
    box = max(0, x), max(0, y), min(iw, x1), min(ih, y1)
    top = doc.y + 4
    mp = photo.draw(c, box, M, top, 357, 591, px=2100, center=True)
    place_badges(c, photo, mp, regions)
    sx = M + 371
    sw = W - M - sx
    sy = doc.y
    text(c, f"本区 {len(regions)} 处", sx, sy, 12, TEAL, BOLD)
    sy -= 22
    remainder = []
    for index, g in enumerate(regions):
        _, color = region_style(g)
        title = preview(label_of(g), 80)
        badge_w = pdfmetrics.stringWidth(str(g["label"]), BOLD, 7.7) + 9
        lead = 12
        title_width = sw - badge_w - 6
        if sy - len(wrapped(title, title_width, 8.9)) * lead < 106:
            remainder = regions[index:]
            break
        badge(c, g["label"], sx, sy, color, 7.7)
        after = para(c, title, sx + badge_w + 6, sy, title_width, 8.9, lead)
        c.linkRect("", region_key(g), (sx, after + 5, W - M, sy + 10), thickness=0)
        sy = after - 8
    if remainder:
        para(c, "其余编号见下一页索引。", sx, sy, sw, 8.8, 12, MUTED)
    elif not regions:
        para(c, "本区没有保留观察编号。", sx, sy, sw, 8.8, 12, MUTED)
    text(c, f"图幅 x {box[0]}–{box[2]}，y {box[1]}–{box[3]} px", M, 54, 9, MUTED)
    if remainder:
        doc.start("分区图谱", sector_name(number) + " · 区域索引")
        for g in remainder:
            doc.lines(f'{g["label"]}  {label_of(g)}', lead=18, color=TEAL, linked=region_key(g))


def clinical_rows(region):
    diagnosis = region.get("diagnosis") or {}
    phenomenon = region.get("evidence") or region.get("phenomenon") or "未记录具体形态。"
    primary = diagnosis.get("primary") or region.get("type") or "类型待鉴别。"
    components = list(dict.fromkeys(sentence(value) for value in
                                    (primary, diagnosis.get("reason"), diagnosis.get("alternative")) if value))
    verification = (diagnosis.get("verification") or region.get("needs_onsite")
                    or "需要人工对照原图及同位记录，核对可见形态。")
    return [("可见现象", phenomenon), ("病害判断", "".join(components)), ("人工核查方法", verification)]


def suggestion_links(suggestions):
    return [(f'建议 {item["no"]}  {preview(item.get("summary") or item.get("title") or "保护建议", 100)}',
             reference_key(item)) for item in suggestions if item.get("category") in (None, "", "保护")]


def draw_region(doc, photo, number, region, suggestions):
    c = doc.canvas
    kind, section = sector_name(number), "局部证据与病害判读"
    if doc.kind != kind:
        doc.start(kind, section)
    local_left, local_width = M, 182
    text_x = local_left + local_width + 15
    text_width = W - M - text_x
    label_width = 68
    title = preview(label_of(region))
    label = str(region["label"])
    name, color = region_style(region)
    badge_width = pdfmetrics.stringWidth(label, BOLD, 10) + 9
    title_width = BODY - badge_width - 10
    title_lines = wrapped(title, title_width, 14, BOLD)
    rows = clinical_rows(region)
    measures = suggestion_links(suggestions)
    if measures:
        rows.append(("保护措施", "\n".join(item[0] for item in measures)))
    elif region.get("record_only") is True:
        rows.append(("保护措施", "现状记录即可。"))
    text_height = sum(14 * len(wrapped(val, text_width - label_width, 9.6)) + 5 for _, val in rows)
    height = max(233, text_height) + len(title_lines) * 18 + 47
    doc.ensure(min(height, 343))
    c.bookmarkHorizontalAbsolute(region_key(region), doc.y + 13)
    info = [name]
    if photo_basis(region):
        info.append(f"照片依据 {photo_basis(region)}")
    priority = (region.get("diagnosis") or {}).get("priority")
    if priority:
        info.append(f"核查 {priority}")
    badge(c, label, M, doc.y, color, 10)
    doc.y = para(c, title, M + badge_width + 10, doc.y, title_width, 14, 18, INK, BOLD) - 3
    tag = "  /  ".join(info)
    coordinates = coords(region)
    if pdfmetrics.stringWidth(tag, FONT, 9.1) + pdfmetrics.stringWidth(coordinates, FONT, 8.7) < BODY - 12:
        text(c, tag, M, doc.y, 9.1, TEAL)
        text(c, coordinates, W - M, doc.y, 8.7, MUTED, FONT, "right")
        doc.y -= 16
    else:
        doc.lines(tag, size=9.1, lead=13, color=TEAL)
        doc.lines(coordinates, size=8.7, lead=13, color=MUTED)
    top = doc.y
    cp = photo.draw(c, photo.crop_box(region), local_left, top, local_width, 157, px=1380, center=True)
    photo.outline(c, cp, region, dashed=True)
    if region.get("map_marks"):
        photo.mark_region(c, cp, region)
    text(c, "原图局部", local_left, top - 172, 8.5, MUTED)
    loc = photo.location(c, region, local_left, top - 181, 57, 68)
    para(c, "全图位置", loc[0] + loc[5] + 8, top - 198, 95, 8.5, 13, MUTED)
    page = c.getPageNumber()
    first_y = top - 8
    doc.y = first_y
    for field, val in rows:
        if field == "保护措施" and measures:
            for index, (measure, target) in enumerate(measures):
                doc.field(field if index == 0 else "", measure, x=text_x, width=text_width,
                          label_width=label_width, size=9.6, leading=14, linked=target)
        else:
            doc.field(field, val, x=text_x, width=text_width, label_width=label_width, size=9.6, leading=14)
    if c.getPageNumber() == page:
        doc.y = min(doc.y, top - 251)
    rule(c, doc.y + 4)
    doc.y -= 15


def draw_exclusions(doc, case, review):
    findings = caselog.load(case, "01_findings.json", required=False) or {}
    examples = findings.get("rejected") or []
    retained = {r.get("from_candidate") for r in review.get("regions", [])}
    extra = [c for c in review.get("candidates", [])
             if c.get("id") not in retained and c.get("verdict") in {"存疑", "否决"}]
    if not (examples or extra):
        return
    doc.start("影像鉴别", "未纳入区域的候选与成像限制", "excluded")
    for item in examples:
        doc.subheading(item.get("looked_like") or "初筛候选")
        box = item.get("bbox_xywh")
        if box:
            doc.lines("原图坐标 " + ", ".join(map(str, box)) + " px", size=8.9, lead=13, color=MUTED)
        doc.lines(item.get("why_not") or "未记录排除依据。")
    for item in extra:
        tag = f'候选 {item.get("id", "—")}  ·  {item["verdict"]}'
        doc.subheading(f'{tag}  {item.get("type", "")}')
        doc.lines(item.get("evidence") or item.get("reason") or "未记录取舍依据。")


def draw_conservation(doc, advice, suggestions):
    doc.start("保护建议", "对象背景与保护思路", "strategy")
    doc.field("对象背景", advice.get("object_context") or "未提供。")
    doc.field("保护思路", advice.get("overall_strategy") or "未提供。")
    if suggestions:
        doc.subheading("建议目录")
        for item in suggestions:
            stages = " / ".join(str(item[k]) for k in ("stage", "urgency") if item.get(k))
            text_value = f'{item["no"]:02}  {item.get("title", "")}' + (f"  ·  {stages}" if stages else "")
            doc.lines(text_value, linked=reference_key(item), size=10.2, color=TEAL)
            doc.y -= 3
        doc.start("保护建议", "措施、依据与实施前提", "suggestions")
    for item in suggestions:
        name = f'{item["no"]:02}  {item.get("title", "")}'
        tags = " / ".join(str(item[k]) for k in ("category", "stage", "urgency") if item.get(k))
        labels = "、".join(item.get("related_regions") or ())
        rows = [("相关区域", labels or "全幅")]
        rows.extend((label, item[key]) for label, key in (
            ("建议内容", "content"), ("依据", "basis"), ("前提条件", "preconditions"), ("风险", "risk")
        ) if item.get(key))
        block = 48 + 20 * len(wrapped(display_copy(name), BODY, 13, BOLD))
        block += sum(15.5 * len(wrapped(display_copy(value), BODY - 73, 10.6)) + 4.5 for _, value in rows)
        doc.ensure(block if block < 610 else 78)
        doc.canvas.bookmarkHorizontalAbsolute(reference_key(item), doc.y + 15)
        doc.subheading(name)
        doc.lines(tags, size=9.5, lead=14, color=MUTED)
        for label, value in rows:
            doc.field(label, value)
        rule(doc.canvas, doc.y + 4)
        doc.y -= 13
    doc.start("保护建议", "待核查事项与参考资料", "references")
    for heading, key in (("证据缺口", "uncertainty"), ("待核查事项", "human_check_points"), ("参考资料", "references")):
        values = advice.get(key) or []
        if not values:
            continue
        doc.subheading(heading)
        for i, value in enumerate(values, 1):
            if isinstance(value, dict):
                desc = sentence(value.get("name", "")) + str(value.get("note") or "")
                doc.field(f"{i:02}", desc, label_width=27, url=value.get("url"))
            else:
                doc.field(f"{i:02}", str(value), label_width=27)
        doc.y -= 8
    doc.lines("实体处理的必要性、材料和工艺由负责的文物保护人员经现场评估及必要试验确定。",
              size=9.5, color=MUTED)


def render(case, path, title):
    meta = caselog.load(case, "case_meta.json")
    review = caselog.load(case, "02_review.json")
    advice = caselog.load(case, "03_conservation.json")
    photo = Photo(caselog.input_image(case))
    regions = review.get("regions") or []
    suggestions = advice.get("suggestions") or []
    sectors = {n: [] for n in range(1, 10)}
    for g in regions:
        sectors[tile_number(photo, g)].append(g)
    by_region = {g["label"]: [] for g in regions}
    for suggestion in suggestions:
        for label in suggestion.get("related_regions") or []:
            if label in by_region:
                by_region[label].append(suggestion)
    doc = Report(path, title)
    sectors = {number: items for number, items in sectors.items() if items}
    draw_cover(doc, title, photo, regions, suggestions, meta, review, advice, sectors)
    draw_scope(doc, review, sectors)
    for number, items in sectors.items():
        draw_tile(doc, photo, number, items)
        for region in items:
            draw_region(doc, photo, number, region, by_region[region["label"]])
    draw_exclusions(doc, case, review)
    draw_conservation(doc, advice, suggestions)
    return doc.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("--title", default="壁画病害识别与保护建议报告")
    args = parser.parse_args()
    output = args.case / "03_report.pdf"
    total = render(args.case, output, args.title)
    caselog.log(args.case, "② 病害识别与保护建议报告", "make_report.py（非 AI）",
                ["02_review.json", "03_conservation.json", "00_input"], [output.name], f"PDF {total} 页（AI 草稿）")
    print(f"已生成 {output.name}（{total} 页）。人工复核单由 mural-review-pdf 另行生成。")


if __name__ == "__main__":
    main()
