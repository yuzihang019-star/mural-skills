"""Generate a printable review form with one entry per AI draft item.

usage: python make_form.py <case_dir> [--force] [--title "壁画病害人工复核单"]
Writes:
  04_review_form.pdf    cover + one page per item (crop, location, AI draft, decision boxes) + sign-off page
  04_human_review.json  the record the reviewer's decisions are entered into
  04_review_form.md     plain-text checklist of the same items
"""
import argparse
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caselog  # noqa: E402

REGION_KEYS = ("phenomenon", "type", "evidence", "impact", "confidence", "needs_onsite")
SUG_KEYS = ("category", "stage", "urgency", "title", "content", "related_regions", "basis", "preconditions", "risk")
DIAGNOSIS_LABELS = {
    "primary": "首要判读",
    "reason": "区分依据",
    "alternative": "替代解释",
    "verification": "专项核查",
    "confidence": "照片依据",
    "priority": "核查优先级",
}
FIELD_LABELS = {
    "phenomenon": "可见现象", "type": "暂定类型", "evidence": "图像证据", "impact": "影响",
    "confidence": "照片依据", "needs_onsite": "人工核查方法",
    "category": "类别", "stage": "阶段", "urgency": "紧迫度", "title": "标题", "content": "建议内容",
    "related_regions": "相关区域", "basis": "依据", "preconditions": "前提条件", "risk": "风险",
}
TEXT_ITEMS = (("object_context", "对象背景与已知条件"), ("overall_strategy", "整体保护思路"))
LIST_ITEMS = (("uncertainty", "不确定性"), ("human_check_points", "待核查事项"))
PHOTO_BASIS = {"高": "较清楚", "中": "有限", "低": "较弱"}


def build_items(r, a):
    items = [{"key": "overall", "kind": "整体观察与评估范围", "ai": r["overall_observation"]}]
    for g in r["regions"]:
        ai = {k: g.get(k, "") for k in REGION_KEYS}
        if "diagnosis" in g:
            ai["diagnosis"] = g["diagnosis"]
        item = {"key": f"region:{g['label']}", "kind": f"病害区域 {g['label']}",
                "ai": ai, "bbox_xywh": g["bbox_xywh"]}
        if g.get("map_marks"):
            item["map_marks"] = g["map_marks"]
        items.append(item)
    for key, kind in TEXT_ITEMS:
        if str(a.get(key) or "").strip():
            items.append({"key": key, "kind": kind, "ai": a[key]})
    for s in a["suggestions"]:
        items.append({"key": f"suggestion:{s['no']}", "kind": f"保护建议 {s['no']}",
                      "ai": {k: s.get(k, "") for k in SUG_KEYS if k in s}})
    for key, kind in LIST_ITEMS:
        if a.get(key):
            items.append({"key": key, "kind": kind, "ai": a[key]})
    for it in items:
        it.update({"decision": "", "revised": None, "note": ""})
    return items


def fmt(v, markdown=False):
    if isinstance(v, dict):
        diagnosis = v.get("diagnosis")
        has_diagnosis = isinstance(diagnosis, dict)
        base = "；".join(f"{FIELD_LABELS.get(k, k)}　{display_value(k, v[k])}" for k in v
                        if k != "diagnosis" and (k != "confidence" or not has_diagnosis)
                        and v[k] not in ("", None, []))
        if has_diagnosis:
            lines = [f"{title}　{display_value(k, diagnosis.get(k, '未填写'))}" for k, title in DIAGNOSIS_LABELS.items()]
            if markdown:
                return base + "\n\n" + "\n".join(f"- {line}" for line in lines)
            return "\n".join([base, *lines])
        return base
    if isinstance(v, list):
        return "；".join(reader_text(x) for x in v)
    return reader_text(v)


def reader_text(value):
    return str(value).replace("判读置信度", "照片依据").replace("置信度", "照片依据")


def display_value(key, value):
    if key == "confidence" and isinstance(value, str):
        return PHOTO_BASIS.get(value, value)
    return fmt(value)


def region_title(region):
    return region.get("map_title") or f"区域 {region['label']} 的影像观察"


def layout_rows(item, linked):
    """Use reader-facing headings without changing the transcribed draft fields."""
    key, value = item["key"], item["ai"]
    if key.startswith("region:"):
        label = key.split(":", 1)[1]
        diagnosis = value.get("diagnosis") or {}
        judgment = ""
        for entry in (diagnosis.get("primary") or value.get("type") or "待人工核查",
                      diagnosis.get("reason"), diagnosis.get("alternative")):
            if entry and entry.strip().rstrip("。") and entry.strip().rstrip("。") not in judgment:
                entry = entry.strip()
                judgment += entry if entry[-1] in "。！？.!?" else entry + "。"
        rows = [
            ("可见现象", value.get("evidence") or value.get("phenomenon") or "待补充", None),
            ("病害判断", judgment, None),
            ("人工核查方法", diagnosis.get("verification") or value.get("needs_onsite") or "请对照原图核查。", None),
        ]
        for i, entry in enumerate(linked.get(label, [])):
            rows.append(("保护措施" if i == 0 else "", f"建议 {entry['no']}　{entry['title']}（查阅）",
                         f"suggestion:{entry['no']}"))
        if not linked.get(label):
            rows.append(("保护措施", "请参照整体保护思路及保护建议页。", None))
        return rows
    if key.startswith("suggestion:"):
        tags = "  /  ".join(v for v in (value.get("category"), value.get("stage"),
                                          "紧迫度 " + value["urgency"] if value.get("urgency") else "") if v)
        return [
            ("建议", value.get("title", ""), None),
            ("阶段", tags, None),
            ("相关区域", value.get("related_regions") or "整体", None),
            ("保护措施", value.get("content", ""), None),
            ("依据", value.get("basis", ""), None),
            ("实施前提", value.get("preconditions", ""), None),
            ("风险", value.get("risk", ""), None),
        ]
    if isinstance(value, list):
        return [(f"{i:02}", str(entry), None) for i, entry in enumerate(value, 1)] or [("内容", "无条目。", None)]
    return [("AI 草稿", str(value), None)]


def row_text(value):
    return reader_text("、".join(value) if isinstance(value, list) else value)


def merge_existing(items, existing):
    """Keep human entries only when each reviewed AI draft still matches."""
    if existing is None:
        return {"items": items}
    fresh = {it["key"]: it for it in items}
    previous = existing.get("items", [])
    seen = set()
    legacy = []
    for old in previous:
        key = old.get("key")
        if key in seen:
            raise SystemExit(f"既有复核记录中有重复条目 {key}，请先核对记录。")
        seen.add(key)
        current = fresh.get(key)
        if current is None and key in ("uncertainty", "human_check_points") and old.get("ai") == []:
            legacy.append(dict(old))
            continue
        if (current is None or current["ai"] != old.get("ai")
                or current.get("bbox_xywh") != old.get("bbox_xywh")
                or (current.get("map_marks") or []) != (old.get("map_marks") or [])):
            raise SystemExit(f"既有复核条目 {key} 的 AI 草稿、位置或标记已变动。请保留原复核记录并为新草稿另建案例。")
        current.update({k: old[k] for k in ("decision", "revised", "note") if k in old})
    if fresh.keys() - seen:
        raise SystemExit("本次草稿包含新的复核条目。请保留原复核记录并为新草稿另建案例。")
    return {**existing, "items": items + legacy}


def render_pdf(case, items, path, title):
    from pdf_style import (A4, BODY, BOLD, Canvas, FONT, H, INK, M, MUTED, PALE, RULE, TEAL, W,
                           Photo, coords, finish, header, para, photo_basis, rule, text, wrapped)
    case = Path(case)
    photo = Photo(caselog.input_image(case))
    meta = caselog.load(case, "case_meta.json")
    review = caselog.load(case, "02_review.json")
    advice = caselog.load(case, "03_conservation.json")
    regions = {region["label"]: region for region in review["regions"]}
    linked = {label: [] for label in regions}
    for suggestion in advice["suggestions"]:
        for label in set(suggestion.get("related_regions") or ()):
            if label in linked:
                linked[label].append(suggestion)

    page_title = "人工复核单"
    pending = "由实际复核人填写"
    date = caselog.now().split("T", 1)[0]
    row_size, row_leading, label_width = 10.3, 15.3, 83
    list_size, rows_per_column = 10.1, 23
    index_capacity = rows_per_column * 2
    decision_top = 238
    first_region_rows = H - 347
    text_rows = H - 111

    def section_start(c, label, subtitle=page_title):
        return header(c, subtitle, label, pending)

    def close_page(c):
        finish(c, page_title, date)

    def clipped_line(value, width, size, font=FONT):
        lines = wrapped(value, width, size, font)
        if len(lines) <= 1:
            return lines[0] if lines else ""
        first = lines[0].rstrip("。 、")
        while len(wrapped(first + "…", width, size, font)) > 1:
            first = first[:-1]
        return first + "…"

    def split_rows(rows, has_photo):
        # Keep the signature panel clear, including when a single field spans pages.
        top = first_region_rows if has_photo else text_rows
        remaining = top
        pages = [[]]
        for label, value, target in rows:
            if not value:
                continue
            lines = wrapped(row_text(value), BODY - label_width, row_size)
            offset = 0
            while offset < len(lines):
                room = int((remaining - decision_top - 10) / row_leading)
                if room < 1:
                    pages.append([])
                    remaining = text_rows
                    continue
                chunk = lines[offset:offset + room]
                row_label = f"{label}（续）" if offset and label else label
                pages[-1].append((row_label, chunk, target))
                remaining -= len(chunk) * row_leading + 6
                offset += len(chunk)
        return pages

    plans = []
    for item in items:
        key = item["key"]
        region = regions.get(key.split(":", 1)[1]) if key.startswith("region:") else None
        rows = layout_rows(item, linked)
        plans.append((item, region, split_rows(rows, region is not None)))
    entries = len(plans) + 1
    index_count = (entries + index_capacity - 1) // index_capacity
    page = 2 + index_count
    for (item, _, pages) in plans:
        item["pdf_page"] = page
        page += len(pages)
    sign_page = page

    c = Canvas(str(path), pagesize=A4, pageCompression=1)
    c.setTitle(title)
    c.setAuthor("壁画病害人工复核")
    c.setSubject("影像判读及保护建议的人工复核")
    c.bookmarkPage("cover")
    c.addOutlineEntry("封面", "cover")

    cover_titles = wrapped(title, BODY, 22, BOLD)
    title_preview = title if len(cover_titles) <= 2 else "\n".join((cover_titles[0], clipped_line("".join(cover_titles[1:]), BODY, 22, BOLD)))
    y = section_start(c, title_preview)
    text(c, f"{photo.size[0]} × {photo.size[1]} px　 /　 {len(regions)} 个区域　 /　 {len(advice['suggestions'])} 条建议",
         M, y, 10.7, TEAL, BOLD)
    y -= 23
    photo.draw(c, None, M, y, 280, 368, px=1550, center=True)
    side_x = M + 302
    side_width = W - M - side_x
    text(c, "怎样填写", side_x, y - 3, 13.5, TEAL, BOLD)
    side_y = y - 26
    for instruction in (
        "对照原图和可用资料逐项核查。每项最后一页可勾选采纳、修改或否决。整体观察使用采纳或修改。",
        "修改请写明替换内容，否决请写明理由。区域被否决后，请复核引用它的建议。",
        "可打印填写，也可在 PDF 阅读器批注。在末页填写复核范围和签名信息。",
    ):
        side_y = para(c, instruction, side_x, side_y, side_width, 10.5, 17) - 9
    text(c, "打开条目目录", side_x, side_y - 1, 10.6, TEAL, BOLD)
    c.linkRect("", "index:1", (side_x, side_y - 8, W - M, side_y + 9), thickness=0)
    text(c, "基准照片", M, y - 382, 8.7, MUTED)
    y -= 401
    findings = caselog.load(case, "01_findings.json", required=False) or {}
    models = [findings.get("reviewer_model"), review.get("reviewer_model"), advice.get("advisor_model")]
    info = [
        ("基准文件", meta.get("image_name") or Path(caselog.input_image(case)).name),
        ("图像来源", meta.get("image_source") or "未提供"),
        ("机构／项目", meta.get("team") or "未提供"),
        ("模型", "、".join(dict.fromkeys(model for model in models if model)) or "未记录"),
    ]
    for label, value in info:
        text(c, label, M, y, 9.5, TEAL, BOLD)
        lines = wrapped(str(value), BODY - 73, 9.5)
        shown = lines if len(lines) <= 2 else [lines[0], clipped_line(lines[1] + "（完整内容见案例记录）", BODY - 73, 9.5)]
        for line in shown:
            text(c, line, M + 73, y, 9.5, INK, FONT)
            y -= 14
        y -= 4
    close_page(c)

    indexed = [(item["kind"], region_title(region) if region else
                item["ai"].get("title", "") if item["key"].startswith("suggestion:") else "",
                item["key"], item["pdf_page"]) for item, region, _ in plans]
    indexed.append(("复核签署", "", "sign-off", sign_page))
    for index in range(index_count):
        key = f"index:{index + 1}"
        c.bookmarkPage(key)
        c.addOutlineEntry("条目目录" if index_count == 1 else f"条目目录 {index + 1}", key)
        suffix = f"（{index + 1} / {index_count}）" if index_count > 1 else ""
        y = section_start(c, "条目目录" + suffix)
        cw = (BODY - 20) / 2
        section = indexed[index * index_capacity:(index + 1) * index_capacity]
        for local_n, (label, subtitle, destination, target_page) in enumerate(section):
            column, row = divmod(local_n, rows_per_column)
            x = M + column * (cw + 20)
            yy = y - row * 28
            n = index * index_capacity + local_n + 1
            caption = f"{n:03}  {label}" if destination != "sign-off" else label
            text(c, clipped_line(caption, cw - 35, list_size), x, yy, list_size, INK, BOLD)
            text(c, str(target_page), x + cw, yy, list_size, TEAL, FONT, "right")
            if subtitle:
                text(c, clipped_line(subtitle, cw - 13, 8.6), x + 23, yy - 12, 8.6, MUTED)
            rule(c, yy - 17, x, cw)
            c.linkRect("", destination, (x, yy - 17, x + cw, yy + 10), thickness=0)
        close_page(c)

    def check_box(label, x, y):
        c.setStrokeColor(TEAL)
        c.setLineWidth(.8)
        c.rect(x, y - 2, 10.5, 10.5, stroke=1, fill=0)
        text(c, label, x + 15, y, 10.2)

    def writing_lines(x, y, width, count, spacing):
        for i in range(count):
            rule(c, y - i * spacing, x, width)

    def decision_panel(item):
        panel_bottom = 54
        c.setFillColor(PALE)
        c.setStrokeColor(RULE)
        c.setLineWidth(.6)
        c.roundRect(M, panel_bottom, BODY, decision_top - panel_bottom, 7, stroke=1, fill=1)
        x, y = M + 13, decision_top - 23
        text(c, "复核决定（勾选一项）", x, y, 11, TEAL, BOLD)
        options = ("采纳", "修改") if item["key"] == "overall" else ("采纳", "修改", "否决")
        for i, option in enumerate(options):
            check_box(option, x + 163 + i * 85, y)
        text(c, "修改为（可只填写变动字段）", x, y - 23, 9.5, MUTED)
        writing_lines(x, y - 42, BODY - 26, 3, 18)
        note = "理由、依据或所用资料"
        if item["key"] != "overall":
            note += "（否决时必填）"
        text(c, note, x, y - 91, 9.5, MUTED)
        writing_lines(x, y - 109, BODY - 26, 2, 17)
        for label, delta, span in (("本页复核人", 0, 156), ("日期", 168, 125), ("签名或确认标识", 305, 182)):
            text(c, label, x + delta, y - 146, 9.2, MUTED)
            start = x + delta + len(label) * 10 + 3
            rule(c, y - 148, start, x + delta + span - start)

    group_outline = None
    for n, (item, region, pages) in enumerate(plans, 1):
        key = item["key"]
        category = key.split(":", 1)[0]
        if category in ("region", "suggestion") and category != group_outline:
            group_outline = category
            group_key = f"group:{category}"
            c.bookmarkPage(group_key)
            c.addOutlineEntry("病害区域" if category == "region" else "保护建议", group_key)
        c.bookmarkPage(key)
        c.addOutlineEntry(item["kind"], key, level=1 if category in ("region", "suggestion") else 0)
        for j, chunks in enumerate(pages):
            title_ = item["kind"] if j == 0 else f"{item['kind']}（续 {j + 1} / {len(pages)}）"
            section_start(c, title_, f"{page_title}  ·  第 {n} 项")
            if region is not None and j == 0:
                y = H - 111
                text(c, clipped_line(region_title(region), BODY, 12.3), M, y, 12.3, INK, BOLD)
                basis = photo_basis(region)
                priority = (region.get("diagnosis") or {}).get("priority")
                status = "  /  ".join(v for v in (f"照片依据 {basis}" if basis else "", f"核查 {priority}" if priority else "") if v)
                text(c, status, M, y - 19, 9.3, TEAL)
                text(c, coords(region), W - M, y - 19, 8.8, MUTED, FONT, "right")
                top = y - 30
                locator_width = 146
                crop_width = BODY - 16 - locator_width
                crop = photo.draw(c, photo.crop_box(region), M, top, crop_width, 167, px=1525, center=True)
                photo.mark_region(c, crop, region)
                photo.location(c, region, M + crop_width + 16, top, locator_width, 166)
                text(c, "局部放大 · 标记供复核", M, top - 182, 8.7, MUTED)
                text(c, "全图位置", M + crop_width + 16, top - 182, 8.7, MUTED)
            y = first_region_rows if region is not None and j == 0 else text_rows
            for label, lines, target in chunks:
                if label:
                    text(c, label, M, y, row_size, TEAL, BOLD)
                x = M + label_width
                for line in lines:
                    text(c, line, x, y, row_size, TEAL if target else INK)
                    if target:
                        c.linkRect("", target, (x, y - 3, W - M, y + 11), thickness=0)
                    y -= row_leading
                y -= 6
            if j == len(pages) - 1:
                decision_panel(item)
            else:
                text(c, "本项续页 · 复核决定在该项最后一页填写。", M, 63, 9.3, MUTED)
            close_page(c)

    c.bookmarkPage("sign-off")
    c.addOutlineEntry("复核签署", "sign-off")
    y = section_start(c, "复核签署")
    for label in ("复核人", "角色／单位", "复核日期", "签名或确认标识"):
        text(c, label, M, y, 10.8)
        rule(c, y - 5, M + 117, BODY - 117)
        y -= 30
    text(c, "复核范围（可多选）", M, y - 6, 12.2, TEAL, BOLD)
    for i, label in enumerate(("核对原图与文字", "结合档案或项目资料", "结合现场观察", "涉及材料、结构或实体保护判断")):
        check_box(label, M + (i % 2) * 250, y - 29 - (i // 2) * 22)
    y -= 83
    text(c, "录入方式", M, y, 12.2, TEAL, BOLD)
    check_box("复核人本人填写", M, y - 23)
    check_box("按复核人的明确意见转录", M + 250, y - 23)
    y -= 60
    text(c, "采纳 ____ 项　 修改 ____ 项　 否决 ____ 项　 人工新增 ____ 项", M, y, 10.4)
    y -= 36
    text(c, "人工新增的区域、建议或待核查事项", M, y, 12.2, TEAL, BOLD)
    y = para(c, "新增区域请填写独立编号、原图 x、y、w、h、可见现象、暂定类型和判断依据。",
             M, y - 18, BODY, 9.1, 14, MUTED)
    writing_lines(M, y - 3, BODY, 12, 21)
    close_page(c)
    c.save()
    return sign_page


def export_markdown(form, linked, path):
    md = ["# 人工复核清单", "", "对照基准照片和可用资料逐项复核。页码对应 04_review_form.pdf。", ""]
    for n, item in enumerate(form["items"], 1):
        md += [f"## {n}. {item['kind']}（PDF 第 {item['pdf_page']} 页）", ""]
        if "bbox_xywh" in item:
            md += ["原图 x、y、w、h　" + "、".join(map(str, item["bbox_xywh"])), ""]
        for label, value, _ in layout_rows(item, linked):
            if value:
                md.extend([f"**{label}**　{row_text(value)}" if label else row_text(value), ""])
        checks = "、修改" if item["key"] == "overall" else "、修改、否决"
        md += [f"复核决定（勾选一项）　采纳{checks}", "", "修改为／理由", ""]
    md += ["## 人工新增的区域、建议或待核查事项", "", "## 复核签署", "",
           "复核人　　角色　　日期　　复核范围　　签名或确认标识", ""]
    Path(path).write_text("\n".join(md), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--force", action="store_true", help="重新排版并保留同一草稿的已有复核记录")
    ap.add_argument("--title", default="壁画病害人工复核单")
    args = ap.parse_args()
    case = Path(args.case)
    existing = caselog.load(case, "04_human_review.json", required=False)
    if existing is not None and not args.force:
        sys.exit("04_human_review.json 已存在。重新排版并保留同一草稿的复核记录，请加 --force。")
    r = caselog.load(case, "02_review.json")
    a = caselog.load(case, "03_conservation.json")
    form = {
        "_说明": "由实际复核人逐条确认 decision（采纳/修改/否决）。选“修改”时在 revised 写修改后的内容"
                 "（格式与 ai 相同，字典项目和 diagnosis 可只写变动字段）。否决时在 note 写理由。"
                 "pdf_page 为该条在 04_review_form.pdf 中的首页页码。",
        "reviewer": "", "role": "", "reviewed_at": "", "signature": "", "review_scope": "",
        "entered_by": "", "added_regions": [], "added_suggestions": [], "added_notes": [],
        **merge_existing(build_items(r, a), existing),
    }
    linked = {g["label"]: [s for s in a["suggestions"] if g["label"] in (s.get("related_regions") or [])]
              for g in r["regions"]}
    names = "04_review_form.pdf", "04_human_review.json", "04_review_form.md"
    with TemporaryDirectory(prefix=".review-layout-", dir=case) as work:
        out = Path(work)
        total = render_pdf(case, form["items"], out / names[0], args.title)
        caselog.save(out, names[1], form)
        export_markdown(form, linked, out / names[2])
        for name in names:
            os.replace(out / name, case / name)
    caselog.log(case, "③ 人工复核（生成表单）", "make_form.py（非 AI）", ["02_review.json", "03_conservation.json"],
                list(names), f"{len(form['items'])} 个复核条目，PDF {total} 页")
    print(f"已生成 04_review_form.pdf（{total} 页，{len(form['items'])} 项），以及复核记录和文字清单。")


if __name__ == "__main__":
    main()
