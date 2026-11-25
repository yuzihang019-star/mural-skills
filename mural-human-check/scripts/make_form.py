"""Step ④ (start): build the human review form from steps ② and ③.

usage: python make_form.py <case_dir> [--force]
Writes 04_human_review.json (to be filled by a TEAM MEMBER), 04_review_form.md and 04_review_sheet.png.
"""
import argparse
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caselog  # noqa: E402

REGION_KEYS = ("phenomenon", "type", "evidence", "impact", "confidence", "needs_onsite")
SUG_KEYS = ("category", "title", "content", "basis", "risk", "related_regions")


def build_items(r, a):
    items = [{"key": "overall", "kind": "整体观察", "ai": r["overall_observation"]}]
    for g in r["regions"]:
        items.append({"key": f"region:{g['label']}", "kind": f"关注区域 {g['label']}",
                      "ai": {k: g.get(k, "") for k in REGION_KEYS}, "bbox_xywh": g["bbox_xywh"]})
    for s in a["suggestions"]:
        items.append({"key": f"suggestion:{s['no']}", "kind": f"建议 {s['no']}",
                      "ai": {k: s.get(k, "") for k in SUG_KEYS}})
    items.append({"key": "uncertainty", "kind": "不确定性", "ai": a["uncertainty"]})
    items.append({"key": "human_check_points", "kind": "人工复核点", "ai": a["human_check_points"]})
    for it in items:
        it.update({"decision": "", "revised": None, "note": ""})
    return items


def fmt(v):
    if isinstance(v, dict):
        return "；".join(f"{k}: {v[k]}" for k in v if v[k] not in ("", None, []))
    if isinstance(v, list):
        return "；".join(str(x) for x in v)
    return str(v)


def sheet(case, r, items, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    caselog.set_cjk_font()
    rgb = cv2.cvtColor(cv2.imread(caselog.input_image(case)), cv2.COLOR_BGR2RGB)
    H, W = rgb.shape[:2]
    regs = [it for it in items if it["key"].startswith("region:")]
    others = [it for it in items if not it["key"].startswith("region:")]
    n = len(regs)
    fig = plt.figure(figsize=(11, 2.9 * n + 0.35 * sum(len(caselog.wrap(fmt(o["ai"]), 120).split("\n")) + 1 for o in others) + 1.2), dpi=110)
    fig.suptitle("④ 人工复核单（AI 生成内容，待队员逐条 采纳 / 修改 / 否决）", fontsize=15, x=0.02, ha="left", y=0.995)
    top = 1 - 0.9 / fig.get_figheight()
    rowh = 2.9 / fig.get_figheight()
    for i, it in enumerate(regs):
        x, y, w, h = it["bbox_xywh"]
        p = int(max(w, h) * 0.5) + 16
        x0, y0, x1, y1 = max(0, x - p), max(0, y - p), min(W, x + w + p), min(H, y + h + p)
        crop = rgb[y0:y1, x0:x1].copy()
        cv2.rectangle(crop, (x - x0, y - y0), (x - x0 + w, y - y0 + h), (255, 230, 0), max(1, crop.shape[0] // 120))
        ax = fig.add_axes([0.02, top - (i + 1) * rowh + 0.01, 0.22, rowh - 0.02])
        ax.imshow(crop); ax.set_axis_off(); ax.set_title(it["kind"], fontsize=11, loc="left")
        t = "\n".join(caselog.wrap(f"{k}：{v}", 62) for k, v in it["ai"].items() if v)
        fig.text(0.26, top - i * rowh - 0.015, t, va="top", fontsize=9.5)
        fig.text(0.87, top - i * rowh - 0.015, "□ 采纳\n□ 修改\n□ 否决", va="top", fontsize=11)
    y = top - n * rowh - 0.01
    for it in others:
        t = caselog.wrap(f"【{it['kind']}】{fmt(it['ai'])}", 100)
        fig.text(0.02, y, t, va="top", fontsize=9.5)
        fig.text(0.87, y, "□ 采纳 □ 修改 □ 否决", va="top", fontsize=9.5)
        y -= 0.35 * (t.count("\n") + 2) / fig.get_figheight()
    fig.text(0.02, 0.01, "复核人：__________    日期：__________    签字：__________", fontsize=11)
    fig.savefig(path); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case"); ap.add_argument("--force", action="store_true")
    a_ = ap.parse_args()
    case = a_.case
    if os.path.exists(os.path.join(case, "04_human_review.json")) and not a_.force:
        sys.exit("04_human_review.json 已存在（可能已有人工填写），要重建请加 --force")
    r = caselog.load(case, "02_review.json")
    a = caselog.load(case, "03_advice.json")
    items = build_items(r, a)
    form = {"_说明": "由队员本人逐条填写 decision（采纳/修改/否决）。选“修改”时在 revised 写修改后的内容"
                     "（格式与 ai 相同，可只写改动的字段）。AI 不得代填。",
            "reviewer": "", "role": "", "reviewed_at": "", "signature": "",
            "entered_by": "", "items": items,
            "added_regions": [], "added_suggestions": [], "added_notes": []}
    caselog.save(case, "04_human_review.json", form)

    md = ["# ④ 人工复核单", "", "以下内容均由 AI 生成。请队员逐条判断：**采纳 / 修改 / 否决**，修改的写出改后的内容。", ""]
    for it in items:
        md += [f"## {it['kind']}", "", fmt(it["ai"]), "", "- [ ] 采纳　- [ ] 修改　- [ ] 否决", "", "修改为 / 备注：", ""]
    md += ["## 人工新增（模型和 AI 都没发现、但你认为应写进观察卡的内容）", "", "", "---", "",
           "复核人：　　　　角色：　　　　日期：　　　　签字："]
    open(os.path.join(case, "04_review_form.md"), "w", encoding="utf-8").write("\n".join(md))
    sheet(case, r, items, os.path.join(case, "04_review_sheet.png"))
    caselog.log(case, "④ 人工复核（发起）", "make_form.py（非 AI）", ["02_review.json", "03_advice.json"],
                ["04_human_review.json", "04_review_form.md", "04_review_sheet.png"], f"{len(items)} 项待人工复核")
    print(f"已生成复核单：{len(items)} 项待队员复核。")
    print("把 04_review_sheet.png / 04_review_form.md 交给队员，收集其逐条决定后再运行 apply_review.py。")


if __name__ == "__main__":
    main()
