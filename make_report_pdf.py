"""Build an annotated damage-report PDF from a mural-screen case folder.
Usage: python3 make_pdf.py <case_dir> <out_pdf>
Pages are composed with PIL (A4 @ 200 dpi) so Chinese fonts always render."""
import json, sys, os, textwrap
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
case, out = sys.argv[1], sys.argv[2]
W, H = 1654, 2339            # A4 @ 200 dpi
M = 90                       # margin
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONTB = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
def F(sz, b=False): return ImageFont.truetype(FONTB if b else FONT, sz, index=2)  # index 2 = SC

COL = {"脱落类": (220, 30, 40), "裂缝类": (255, 140, 0), "人为损害": (200, 0, 200),
       "污染类": (120, 90, 0), "颜色变化类": (20, 110, 230)}
CONF_W = {"高": 7, "中": 5, "低": 4}

fd = json.load(open(os.path.join(case, "01_findings.json")))
cand = json.load(open(os.path.join(case, "01_candidates.json")))
meta = json.load(open(os.path.join(case, "case_meta.json")))
spot = json.load(open(os.path.join(case, "02x_spotmap.json")))
src = Image.open(os.path.join(case, "00_input.jpg")).convert("RGB")
SW, SH = src.size
findings = fd["findings"]; rejected = cand.get("rejected", [])

def wrap(draw, text, font, width):
    """Wrap CJK/mixed text by pixel width."""
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) > width:
                lines.append(cur); cur = ch
            else:
                cur += ch
        lines.append(cur)
    return lines

def para(draw, xy, text, font, width, fill=(30, 30, 30), gap=8):
    x, y = xy
    for ln in wrap(draw, text, font, width):
        draw.text((x, y), ln, font=font, fill=fill)
        y += font.size + gap
    return y

def dashed_rect(d, box, col, w, dash=18):
    x0, y0, x1, y1 = box
    for (a, b, c, e) in [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]:
        L = max(abs(c - a), abs(e - b)); n = max(1, int(L // dash))
        for i in range(0, n, 2):
            t0, t1 = i / n, min(1, (i + 1) / n)
            d.line([(a + (c - a) * t0, b + (e - b) * t0), (a + (c - a) * t1, b + (e - b) * t1)], fill=col, width=w)

def label(d, x, y, text, col, font):
    tw = d.textlength(text, font=font)
    d.rectangle([x, y, x + tw + 12, y + font.size + 10], fill=col)
    d.text((x + 6, y + 2), text, font=font, fill="white")

def fit(img, mw, mh):
    s = min(mw / img.width, mh / img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS), s

def header(d, title, page):
    d.text((M, 50), title, font=F(44, True), fill=(20, 20, 20))
    d.line([(M, 118), (W - M, 118)], fill=(150, 120, 80), width=3)
    foot = f"壁画病害标注报告 · {meta['image_name']} · 第 {page} 页  |  AI 初筛结果，全部为“疑似”，须经专业人员现场确认"
    d.text((M, H - 70), foot, font=F(22), fill=(110, 110, 110))

pages = []
def new_page():
    p = Image.new("RGB", (W, H), "white"); pages.append(p); return p, ImageDraw.Draw(p)

# ---------- page 1: overview ----------
p, d = new_page(); header(d, "壁画病害标注报告（AI 初筛）", 1)
ov = fd["overall"]
y = 140
y = para(d, (M, y), f"画面内容：{ov['content']}", F(26), W - 2 * M)
y = para(d, (M, y), f"整体状况：{ov['condition']} —— {ov['condition_reason']}", F(26), W - 2 * M)
y += 10
img_h = H - y - 560
thumb, s = fit(src, W - 2 * M, img_h)
ov_img = thumb.copy(); od = ImageDraw.Draw(ov_img)
# draw large boxes first so small ones stay on top
for f in sorted(findings, key=lambda f: -f["bbox_xywh"][2] * f["bbox_xywh"][3]):
    x, yy, w, h = f["bbox_xywh"]; col = COL.get(f["category"], (0, 0, 0))
    box = [x * s, yy * s, (x + w) * s - 1, (yy + h) * s - 1]
    if f["confidence"] == "低": dashed_rect(od, box, col, 3)
    else: od.rectangle(box, outline=col, width=4 if f["confidence"] == "高" else 3)
for f in findings:
    x, yy, w, h = f["bbox_xywh"]; col = COL.get(f["category"], (0, 0, 0))
    label(od, max(0, x * s + 2), max(0, yy * s + 2), f["id"], col, F(22, True))
ox = (W - ov_img.width) // 2
p.paste(ov_img, (ox, y)); y += ov_img.height + 14
# legend
lx = M
for k, c in COL.items():
    d.rectangle([lx, y + 6, lx + 30, y + 30], fill=c); d.text((lx + 38, y), k, font=F(24), fill=(40, 40, 40))
    lx += 60 + d.textlength(k, font=F(24)) + 20
d.text((lx + 10, y), "实线=信心中/高（粗线=高）  虚线=信心低", font=F(24), fill=(40, 40, 40)); y += 50
# summary table
for hx, ht in [(0, "编号"), (70, "病害类型（疑似）"), (820, "位置/范围（原图像素 x,y,宽,高）"), (1300, "信心")]:
    d.text((M + hx, y), ht, font=F(22, True), fill=(60, 60, 60))
y += 34
for f in findings:
    x, yy, w, h = f["bbox_xywh"]
    t = f["type"] if len(f["type"]) <= 22 else f["type"][:21] + "…"
    d.text((M, y), f["id"], font=F(22, True), fill=COL.get(f["category"], (0, 0, 0)))
    d.text((M + 70, y), t, font=F(22), fill=(30, 30, 30))
    d.text((M + 820, y), f"{x},{yy},{w},{h}", font=F(22), fill=(30, 30, 30))
    d.text((M + 1300, y), f["confidence"], font=F(22), fill=(30, 30, 30))
    y += 30

# ---------- page 2: spot statistics ----------
p, d = new_page(); header(d, "附图：身光素面区小斑点自动统计", 2)
y = 140
y = para(d, (M, y), f"方法：{spot['method']}。", F(26), W - 2 * M)
y = para(d, (M, y), f"结果：共找到 {spot['count']} 处小斑点（左身光 {spot['left']} 处，右身光 {spot['right']} 处），"
         f"约占统计区域面积的 {spot['spot_area_frac']*100:.1f}%。蓝线 = 统计区域，红框 = 每个斑点。", F(26), W - 2 * M)
y = para(d, (M, y), f"注意：{spot['note']}。蓝线区域下部延伸到了袈裟下摆的浅色区，那一部分的斑点同样只作参考。这张图对应 F2、F3、F4，"
         "可以帮助说明“点状脱落数量多、分布广”，但数字本身不能当作病害面积。", F(26), W - 2 * M, fill=(150, 40, 40))
sm = Image.open(os.path.join(case, "02x_spotmap_full.jpg")).convert("RGB")
sm, _ = fit(sm, W - 2 * M, H - y - 120)
p.paste(sm, ((W - sm.width) // 2, y + 10))

# ---------- finding detail pages: 2 per page ----------
def crop_for(b, pad_frac=0.25, min_side=500):
    x, y, w, h = b
    pad = int(max(w, h) * pad_frac)
    cx0, cy0 = max(0, x - pad), max(0, y - pad)
    cx1, cy1 = min(SW, x + w + pad), min(SH, y + h + pad)
    if cx1 - cx0 < min_side:
        c = (cx0 + cx1) // 2; cx0, cx1 = max(0, c - min_side // 2), min(SW, c + min_side // 2)
    if cy1 - cy0 < min_side:
        c = (cy0 + cy1) // 2; cy0, cy1 = max(0, c - min_side // 2), min(SH, c + min_side // 2)
    return cx0, cy0, cx1, cy1

FIELDS = [("类型", "type"), ("大类", "category"), ("信心", "confidence"), ("照片可判程度", "photo_grade"),
          ("看到了什么", "evidence"), ("露出层", "layer_exposed"), ("其他可能 / 排除理由", "alternatives"),
          ("怎么核实", "how_to_verify")]
page_no = 3
slot_h = (H - 140 - 100) // 2
for i in range(0, len(findings), 2):
    p, d = new_page(); header(d, "病害逐条说明", page_no); page_no += 1
    for j, f in enumerate(findings[i:i + 2]):
        top = 140 + j * slot_h + 10
        col = COL.get(f["category"], (0, 0, 0))
        cx0, cy0, cx1, cy1 = crop_for(f["bbox_xywh"])
        cr = src.crop((cx0, cy0, cx1, cy1))
        cr, cs = fit(cr, 700, slot_h - 40)
        cd = ImageDraw.Draw(cr)
        x, yy, w, h = f["bbox_xywh"]
        box = [(x - cx0) * cs, (yy - cy0) * cs, (x + w - cx0) * cs - 1, (yy + h - cy0) * cs - 1]
        if f["confidence"] == "低": dashed_rect(cd, box, col, 4)
        else: cd.rectangle(box, outline=col, width=5)
        p.paste(cr, (M, top)); d.rectangle([M - 1, top - 1, M + cr.width, top + cr.height], outline=(180, 180, 180))
        d.text((M, top + cr.height + 4), f"截取范围 x {cx0}–{cx1}, y {cy0}–{cy1}", font=F(20), fill=(120, 120, 120))
        tx = M + 730; tw = W - M - tx; ty = top
        label(d, tx, ty, f["id"], col, F(34, True)); ty += 64
        for name, key in FIELDS:
            val = f.get(key, "")
            if not val: continue
            d.text((tx, ty), name, font=F(23, True), fill=(110, 80, 40)); ty += 32
            ty = para(d, (tx, ty), val, F(23), tw, gap=6) + 8
        if j == 0 and len(findings[i:i + 2]) == 2:
            d.line([(M, 140 + slot_h), (W - M, 140 + slot_h)], fill=(220, 220, 220), width=2)

# ---------- last page: excluded + notes ----------
p, d = new_page(); header(d, "已排除的“像病害但不是”的地方 & 说明", page_no)
y = 140
d.text((M, y), "下面这些地方乍看像病害，核对后判断是原画内容或照片问题，没有计入：", font=F(26), fill=(30, 30, 30)); y += 50
for k, r in enumerate(rejected):
    x, yy, w, h = r["bbox_xywh"]
    cx0, cy0, cx1, cy1 = crop_for(r["bbox_xywh"], 0.3, 400)
    cr, cs = fit(src.crop((cx0, cy0, cx1, cy1)), 230, 230)
    ImageDraw.Draw(cr).rectangle([(x - cx0) * cs, (yy - cy0) * cs, (x + w - cx0) * cs - 1, (yy + h - cy0) * cs - 1],
                                 outline=(90, 90, 90), width=3)
    p.paste(cr, (M, y))
    ty = para(d, (M + 260, y), f"X{k+1}  看起来像：{r['looked_like']}", F(24, True), W - 2 * M - 260)
    ty = para(d, (M + 260, ty + 4), f"为什么不算：{r['why_not']}", F(24), W - 2 * M - 260)
    d.text((M + 260, ty + 4), f"位置 x,y,宽,高 = {x},{yy},{w},{h}", font=F(20), fill=(120, 120, 120))
    y += max(cr.height, ty - y + 30) + 26
y += 10
d.line([(M, y), (W - M, y)], fill=(150, 120, 80), width=2); y += 20
d.text((M, y), "使用说明（请务必看）", font=F(30, True), fill=(20, 20, 20)); y += 52
notes = [
    f"1. 照片问题：{fd['overall']['photo_issues']}",
    "2. 本报告里所有病害都是“疑似”，是 AI 看照片得出的初步判断，不是鉴定结论。起甲、空鼓、酥碱等需要侧光、敲击或现场检测，照片看不出来，所以本报告没有判。",
    "3. 框只表示“大概在这一片”，大框（如 F2、F3、F4、F9、F13）是一整片区域，不是精确轮廓；框的面积不等于病害面积。",
    "4. 信心“低”的条目（虚线框）最容易出错，优先请专业人员现场核实。",
    f"5. 工具与来源：病害识别 = {fd.get('reviewer_model','Claude')} 按 mural-screen v2 识别手册看图；小模型提示 = PixelMLP 像素分类器（自训练于 MuralDH 数据集，测试集像素 F1≈0.18，只作提示）；斑点统计 = OpenCV 图像处理。",
    f"6. 图片来源：{meta.get('image_source','待补')}。对外使用前请补全图片出处和授权。",
]
for n in notes:
    y = para(d, (M, y), n, F(24), W - 2 * M, gap=6) + 12

pages[0].save(out, save_all=True, append_images=pages[1:], resolution=200.0, quality=88)
print("pages", len(pages), out)
