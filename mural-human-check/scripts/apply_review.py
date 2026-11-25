"""Step ④ (finish): apply the team member's decisions -> 04_final.json + 04_change_log.md.

usage: python apply_review.py <case_dir>
Refuses to run unless every item has a decision and the reviewer/signature fields are filled.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caselog  # noqa: E402

DEC = {"采纳", "修改", "否决"}
PROV = {"采纳": "AI 生成 · 人工采纳", "修改": "AI 初稿 · 人工修改"}


def fmt(v):
    if isinstance(v, dict):
        return "；".join(f"{k}: {v[k]}" for k in v if v[k] not in ("", None, []))
    if isinstance(v, list):
        return "；".join(str(x) for x in v)
    return str(v)


def merged(it):
    if it["decision"] == "采纳":
        return it["ai"]
    rv = it["revised"]
    if isinstance(it["ai"], dict) and isinstance(rv, dict):
        out = dict(it["ai"]); out.update(rv); return out
    return rv


def main():
    case = sys.argv[1]
    f = caselog.load(case, "04_human_review.json")
    r = caselog.load(case, "02_review.json")
    a = caselog.load(case, "03_advice.json")
    meta = caselog.load(case, "case_meta.json")
    errs = []
    for k in ("reviewer", "reviewed_at", "signature", "entered_by"):
        if not str(f.get(k, "")).strip():
            errs.append(f"{k} 未填写")
    for it in f["items"]:
        if it.get("decision") not in DEC:
            errs.append(f"{it['kind']}：decision 须为 采纳/修改/否决")
        elif it["decision"] == "修改" and not it.get("revised"):
            errs.append(f"{it['kind']}：选了“修改”但 revised 为空")
    if errs:
        print("人工复核未完成，不能生成最终结果：\n  " + "\n  ".join(errs))
        sys.exit(1)

    regions, sugs, log_rows = [], [], []
    bbox = {g["label"]: g["bbox_xywh"] for g in r["regions"]}
    final = {"overall_observation": "", "overall_provenance": "", "uncertainty": [], "human_check_points": []}
    for it in f["items"]:
        d = it["decision"]
        log_rows.append((it["kind"], d, fmt(it["ai"]), "（已删除）" if d == "否决" else fmt(merged(it)), it.get("note", "")))
        if d == "否决":
            continue
        val, prov = merged(it), PROV[d]
        if it["key"] == "overall":
            final["overall_observation"], final["overall_provenance"] = val, prov
        elif it["key"].startswith("region:"):
            lab = it["key"].split(":")[1]
            regions.append(dict(val, label=lab, bbox_xywh=val.get("bbox_xywh", bbox[lab]), provenance=prov))
        elif it["key"].startswith("suggestion:"):
            sugs.append(dict(val, provenance=prov))
        else:
            final[it["key"]] = [dict(text=t, provenance=prov) for t in (val if isinstance(val, list) else [val]) if t]
    for g in f.get("added_regions", []):
        regions.append(dict(g, provenance="人工新增"))
        log_rows.append(("新增区域", "人工新增", "", fmt(g), ""))
    for s in f.get("added_suggestions", []):
        sugs.append(dict(s, provenance="人工新增"))
        log_rows.append(("新增建议", "人工新增", "", fmt(s), ""))
    for t in f.get("added_notes", []):
        final["human_check_points"].append({"text": t, "provenance": "人工新增"})
        log_rows.append(("新增复核点", "人工新增", "", t, ""))

    # relabel regions A, B, C in order; keep suggestions' references consistent
    remap = {}
    for i, g in enumerate(regions):
        new = "ABC"[i] if i < 3 else str(i + 1)
        remap[g["label"]] = new; g["label"] = new
    for s in sugs:
        s["related_regions"] = [remap[x] for x in s.get("related_regions", []) if x in remap]
    probs = []
    if not 1 <= len(regions) <= 3:
        probs.append(f"复核后关注区域 {len(regions)} 处，观察卡要求 1–3 处")
    if not 1 <= len(sugs) <= 2:
        probs.append(f"复核后建议 {len(sugs)} 条，观察卡要求 1–2 条")
    for g in regions:
        if not all(g.get(k) for k in ("phenomenon", "type", "bbox_xywh")):
            probs.append(f"区域 {g['label']} 缺 phenomenon/type/bbox_xywh")
    if probs:
        print("复核结果不满足观察卡要求：\n  " + "\n  ".join(probs))
        sys.exit(1)

    tools = []
    for rec in caselog.read_log(case):
        if rec["tool"] not in tools and "非 AI" not in rec["tool"]:
            tools.append(rec["tool"])
    final.update({"meta": meta, "regions": regions, "suggestions": sugs,
                  "references": a.get("references", []),
                  "ai_models": {"screen": "PixelMLP 离线筛查模型（自训练）", "review": r.get("reviewer_model", ""),
                                "advise": a.get("advisor_model", "")},
                  "tools_from_log": tools,
                  "human_review": {k: f[k] for k in ("reviewer", "role", "reviewed_at", "signature", "entered_by")},
                  "review_stats": {d: sum(1 for it in f["items"] if it["decision"] == d) for d in DEC} |
                                  {"人工新增": len(f.get("added_regions", [])) + len(f.get("added_suggestions", [])) + len(f.get("added_notes", []))}})
    caselog.save(case, "04_final.json", final)

    md = ["# ④ 人工复核修改记录", "",
          f"复核人：{f['reviewer']}（{f.get('role', '')}）　日期：{f['reviewed_at']}　签字：{f['signature']}　录入方式：{f['entered_by']}", "",
          "| 项目 | 决定 | AI 原文 | 最终内容 | 备注 |", "|---|---|---|---|---|"]
    for row in log_rows:
        md.append("| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in row) + " |")
    open(os.path.join(case, "04_change_log.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    st = final["review_stats"]
    caselog.log(case, "④ 人工复核（完成）", f"人工：{f['reviewer']}", ["04_human_review.json"],
                ["04_final.json", "04_change_log.md"],
                f"采纳{st['采纳']} / 修改{st['修改']} / 否决{st['否决']} / 新增{st['人工新增']}；录入：{f['entered_by']}")
    print(f"完成：采纳 {st['采纳']}，修改 {st['修改']}，否决 {st['否决']}，人工新增 {st['人工新增']}。"
          f"最终 {len(regions)} 处区域、{len(sugs)} 条建议。")


if __name__ == "__main__":
    main()
