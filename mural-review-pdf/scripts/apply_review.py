"""Step ③ (finish): apply the reviewer's decisions -> 04_final.json + 04_change_log.md.

usage: python apply_review.py <case_dir>
Refuses to run unless every item has a decision and the reviewer/signature fields are filled.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caselog  # noqa: E402
from make_form import DIAGNOSIS_LABELS, TEXT_ITEMS, build_items, fmt  # noqa: E402

DEC = {"采纳", "修改", "否决"}
PROV = {"采纳": "AI 生成 · 人工采纳", "修改": "AI 初稿 · 人工修改"}


def merged(it):
    if it["decision"] == "采纳":
        return it["ai"]
    original = it["ai"]
    rv = it["revised"]
    if isinstance(original, dict) and isinstance(rv, dict):
        result = {**original, **rv}
        if it["key"].startswith("region:") and isinstance(rv.get("diagnosis"), dict):
            before = original.get("diagnosis")
            if isinstance(before, dict):
                result["diagnosis"] = {**before, **rv["diagnosis"]}
        return result
    return rv


def text_filled(value):
    return isinstance(value, str) and bool(value.strip())


def valid_diagnosis(value):
    return (
        isinstance(value, dict)
        and value.keys() == DIAGNOSIS_LABELS.keys()
        and all(text_filled(field) for field in value.values())
        and value["confidence"] in ("高", "中", "低")
        and value["priority"] in ("优先", "常规", "随访")
    )


def valid_box(value, image_size):
    if not isinstance(value, list) or len(value) != 4 or any(type(v) is not int for v in value):
        return False
    x, y, w, h = value
    width, height = image_size
    return x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= width and y + h <= height


def main():
    case = sys.argv[1]
    f = caselog.load(case, "04_human_review.json")
    r = caselog.load(case, "02_review.json")
    a = caselog.load(case, "03_conservation.json")
    meta = caselog.load(case, "case_meta.json")
    errs = []
    for k in ("reviewer", "reviewed_at", "signature", "entered_by"):
        if not text_filled(f.get(k)):
            errs.append(f"{k} 未填写")
    expected = {item["key"]: item for item in build_items(r, a)}
    items = f.get("items", [])
    keys = [item.get("key") for item in items]
    if len(set(keys)) != len(keys):
        errs.append("复核单包含重复项目")
    missing = expected.keys() - set(keys)
    if missing:
        errs.append("复核单缺少项目：" + "、".join(sorted(missing)))
    for it in items:
        key = it.get("key")
        # Early versions added these two review items even when their values were empty.
        legacy_empty = key in ("uncertainty", "human_check_points") and not it.get("ai")
        original = expected.get(key)
        if original is None and not legacy_empty:
            errs.append(f"复核单包含不属于本次评估的项目：{key}")
        elif original is not None and (it.get("ai") != original["ai"] or
                                       it.get("bbox_xywh") != original.get("bbox_xywh") or
                                       it.get("map_marks", []) != original.get("map_marks", [])):
            errs.append(f"{key} 的 AI 草稿或区域位置已变更，请核对并按本次版本复核")
        if it.get("decision") not in DEC:
            errs.append(f"{key}：decision 须为 采纳/修改/否决")
        elif it["decision"] == "修改":
            before, after = it.get("ai"), it.get("revised")
            if type(before) is not type(after) or not after or (isinstance(after, str) and not after.strip()):
                errs.append(f"{key}：revised 须填写与 AI 草稿同类型的修改内容")
    # The signed scope statement is still necessary when no region or recommendation is recordable.
    overall = next((item for item in items if item.get("key") == "overall"), None)
    if overall and overall.get("decision") == "否决":
        errs.append("请用“修改”记录复核人确认的整体观察和可评范围，包括无法判断的情况")
    if errs:
        print("人工复核未完成，不能生成最终结果：\n  " + "\n  ".join(errs))
        sys.exit(1)

    regions, sugs, log_rows = [], [], []
    by_label = {g["label"]: g for g in r["regions"]}
    final = {"overall_observation": "", "overall_provenance": "", "uncertainty": [], "human_check_points": []}
    text_keys = {k for k, _ in TEXT_ITEMS}
    for k in text_keys:
        final[k], final[k + "_provenance"] = "", ""
    for it in items:
        d = it["decision"]
        log_rows.append((it["kind"], d, fmt(it["ai"]), "（已删除）" if d == "否决" else fmt(merged(it)), it.get("note", "")))
        if d == "否决":
            continue
        val, prov = merged(it), PROV[d]
        if it["key"] == "overall":
            final["overall_observation"], final["overall_provenance"] = val, prov
        elif it["key"] in text_keys:
            final[it["key"]], final[it["key"] + "_provenance"] = val, prov
        elif it["key"].startswith("region:"):
            lab = it["key"].split(":", 1)[1]
            original_region = by_label[lab]
            region = dict(val, label=lab, bbox_xywh=val.get("bbox_xywh", original_region["bbox_xywh"]), provenance=prov)
            if "map_marks" not in region and original_region.get("map_marks"):
                region["map_marks"] = original_region["map_marks"]
            regions.append(region)
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

    probs = []
    labels = set()
    for g in regions:
        label = g.get("label")
        if not text_filled(label) or label in labels:
            probs.append(f"区域编号缺失或重复：{label}")
        else:
            labels.add(label)
        if not all(text_filled(g.get(k)) for k in ("phenomenon", "type", "evidence")):
            probs.append(f"区域 {label} 缺 phenomenon/type/evidence")
        if "diagnosis" in g and not valid_diagnosis(g["diagnosis"]):
            probs.append(f"区域 {label} 的 diagnosis 须填写病害判断、依据、其他解释、人工核查方法、"
                         "照片依据（JSON 用高/中/低）和核查优先级（优先/常规/随访）")
        if not valid_box(g.get("bbox_xywh"), meta["size_wh"]):
            probs.append(f"区域 {label} 的 bbox_xywh 须是原图内的有效整数坐标")
        elif "map_marks" in g:
            probs.extend(f"区域 {label} 的 {message}。请核对标注；需要移除时明确填写空数组。"
                         for message in caselog.map_marks_errors(g["map_marks"], g["bbox_xywh"]))
    for i, sug in enumerate(sugs, 1):
        if not all(text_filled(sug.get(k)) for k in ("category", "urgency", "title", "content", "basis", "risk")):
            probs.append(f"建议 {i} 缺类别、紧迫度、标题、内容、依据或风险")
        if sug.get("category") == "保护" and not all(text_filled(sug.get(k)) for k in ("stage", "preconditions")):
            probs.append(f"建议 {i} 为保护类，须有阶段和前提条件")
        related = sug.get("related_regions", [])
        if not isinstance(related, list) or any(not text_filled(label) for label in related):
            probs.append(f"建议 {i} 的 related_regions 须为区域编号列表")
        elif set(related) - labels:
            removed = "、".join(sorted(set(related) - labels))
            probs.append(f"建议 {i} 仍引用未保留区域 {removed}，请由复核人改写依据或否决该建议")
    if probs:
        print("复核结果仍有缺项或引用冲突：\n  " + "\n  ".join(probs))
        sys.exit(1)

    findings = caselog.load(case, "01_findings.json", required=False) or {}
    candidates = caselog.load(case, "01_candidates.json", required=False) or {}
    screen_model = findings.get("reviewer_model") or candidates.get("model", "")
    hints_used = candidates.get("small_model_hints_used")
    if "small_model_hints_used" in findings:
        hints_used = findings["small_model_hints_used"]
    elif findings.get("manual_version") in ("mural-screen v2",):
        recorded_hint = any("小模型提示" in f.get("source", "") for f in findings.get("findings", []))
        hints_used = True if recorded_hint else None
    tools = []
    for rec in caselog.read_log(case):
        tool = rec["tool"]
        if tool not in tools and "非 AI" not in tool and not tool.startswith("人工："):
            tools.append(tool)
    final.update({"meta": meta, "regions": regions, "suggestions": sugs,
                  "references": a.get("references", []),
                  "ai_models": {"screen": screen_model, "review": r.get("reviewer_model", ""),
                                "conserve": a.get("advisor_model", "")},
                  "small_model_hints_used": hints_used,
                  "tools_from_log": tools,
                  "human_review": {k: f.get(k, "") for k in ("reviewer", "role", "reviewed_at", "signature", "review_scope", "entered_by")},
                  "review_stats": {d: sum(1 for it in items if it["decision"] == d) for d in DEC} |
                                  {"人工新增": len(f.get("added_regions", [])) + len(f.get("added_suggestions", [])) + len(f.get("added_notes", []))}})
    caselog.save(case, "04_final.json", final)

    md = ["# ③ 人工复核修改记录", "",
          f"复核人：{f['reviewer']}（{f.get('role', '')}）　日期：{f['reviewed_at']}　签字：{f['signature']}　录入方式：{f['entered_by']}", "",
          f"复核范围：{f.get('review_scope') or '未注明'}", "",
          "| 项目 | 决定 | AI 原文 | 最终内容 | 备注 |", "|---|---|---|---|---|"]
    for row in log_rows:
        md.append("| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in row) + " |")
    with open(os.path.join(case, "04_change_log.md"), "w", encoding="utf-8") as output:
        output.write("\n".join(md) + "\n")
    st = final["review_stats"]
    caselog.log(case, "③ 人工复核（完成）", f"人工：{f['reviewer']}", ["04_human_review.json"],
                ["04_final.json", "04_change_log.md"],
                f"采纳{st['采纳']} / 修改{st['修改']} / 否决{st['否决']} / 新增{st['人工新增']}；录入：{f['entered_by']}")
    print(f"完成：采纳 {st['采纳']}，修改 {st['修改']}，否决 {st['否决']}，人工新增 {st['人工新增']}。"
          f"最终 {len(regions)} 处区域、{len(sugs)} 条建议。")


if __name__ == "__main__":
    main()
