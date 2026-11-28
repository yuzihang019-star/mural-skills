"""Validation rules for the unified output format (references/03_输出格式.md). Shared by check_findings.py and the 百炼 eval."""

import math

CONDITIONS = ("未分级", "无法判断", "好", "一般", "差")
ASSESSMENT_STATUSES = ("可评估", "部分可评估", "不可评估")
CONF = ("高", "中", "低")
GRADES = ("A", "B", "C")
CATS = ("脱落类", "裂缝类", "结构盐分类", "污染类", "颜色变化类", "人为损害", "其他")
CONF_CAP = {"A": "高", "B": "中", "C": "低"}
CONF_RANK = {"低": 0, "中": 1, "高": 2}


def validate(doc, size_wh=None, strict=True):
    """Return (errors, warnings). strict=False is used for model outputs in the eval (only fatal problems are errors)."""
    err, warn = [], []
    ov = doc.get("overall") or {}
    findings = doc.get("findings")
    if not isinstance(findings, list):
        (err if strict else warn).append("findings 必须是数组，无候选时填 []")
        findings = []
    if strict:
        if not doc.get("reviewer_model"):
            err.append("reviewer_model 未填写")
        if not ov.get("content"):
            err.append("overall.content 未填写（对象及影像范围）")
        all_tiles = set(doc.get("tiles_all") or [])
        checked = set(doc.get("tiles_checked") or [])
        excluded = doc.get("tiles_excluded", {})
        if not isinstance(excluded, dict) or any(
            not isinstance(reason, str) or not reason.strip() for reason in excluded.values()
        ):
            err.append("tiles_excluded 必须按分块编号注明未检查原因")
            excluded = {}
        if all_tiles and (checked | excluded.keys()) - all_tiles:
            err.append("分块记录包含未知的分块编号")
        if checked & excluded.keys():
            err.append("同一分块不可同时列为已检查和排除")
        missing = all_tiles - checked - excluded.keys()
        if missing:
            err.append(f"分块缺少检查结果或排除原因：{sorted(missing)}")
        if not findings and not (ov.get("condition_reason") or "").strip():
            err.append("无候选时在 overall.condition_reason 说明已评范围或影像限制")
        status = ov.get("assessment_status")
        if status is not None and status not in ASSESSMENT_STATUSES:
            err.append(f"overall.assessment_status 必须是 {ASSESSMENT_STATUSES}")
        if status in ("部分可评估", "不可评估") and not (ov.get("photo_issues") or "").strip():
            err.append("在 overall.photo_issues 记录受限区域及原因")
        if status == "不可评估" and findings:
            err.append("有可定位的观察现象时，请按实际评估范围选择可评性")
        if "small_model_hints_used" in doc and not isinstance(doc["small_model_hints_used"], bool):
            err.append("small_model_hints_used 必须为布尔值")
    if ov.get("condition") not in CONDITIONS:
        (err if strict else warn).append(f"overall.condition 必须是 {CONDITIONS}")
    W, H = size_wh or doc.get("size_wh") or (None, None)
    seen = set()
    for i, f in enumerate(findings):
        fid = f.get("id") or f"#{i + 1}"
        if strict and not f.get("id"):
            err.append(f"{fid}: 缺少 id")
        if fid in seen:
            err.append(f"{fid}: id 重复")
        seen.add(fid)
        b = f.get("bbox_xywh")
        if not (isinstance(b, (list, tuple)) and len(b) == 4 and
                all(type(v) in (int, float) and math.isfinite(v) for v in b)):
            err.append(f"{fid}: bbox_xywh 必须是 [x,y,w,h] 四个数字")
        else:
            x, y, w, h = b
            if w <= 0 or h <= 0:
                err.append(f"{fid}: 框的宽高必须大于 0")
            if W and H and (x < 0 or y < 0 or x + w > W or y + h > H):
                err.append(f"{fid}: 框超出图像范围 {W}x{H}")
            if W and H and w * h > 0.6 * W * H:
                warn.append(f"{fid}: 框占图像 {w * h / (W * H):.0%}，请核对其是否与受影响范围一致")
        for k in ("type", "evidence", "confidence"):
            if not f.get(k):
                err.append(f"{fid}: 缺少 {k}")
        if strict:
            for k in ("category", "photo_grade", "alternatives", "source"):
                if not f.get(k):
                    err.append(f"{fid}: 缺少 {k}")
        if f.get("confidence") and f["confidence"] not in CONF:
            err.append(f"{fid}: confidence 必须是 高/中/低")
        g = f.get("photo_grade")
        if g and g not in GRADES:
            err.append(f"{fid}: photo_grade 必须是 A/B/C")
        if f.get("category") and f["category"] not in CATS:
            warn.append(f"{fid}: category“{f['category']}”不在 {CATS} 中")
        if g in CONF_CAP and f.get("confidence") in CONF_RANK and CONF_RANK[f["confidence"]] > CONF_RANK[CONF_CAP[g]]:
            err.append(f"{fid}: {g} 级判读的置信度最高为“{CONF_CAP[g]}”")
        if g in ("B", "C") and not f.get("how_to_verify"):
            err.append(f"{fid}: {g} 级判读必须写 how_to_verify（进一步所需的资料或检查）")
        if strict and len(str(f.get("evidence", ""))) < 10:
            warn.append(f"{fid}: evidence 太短，请写出颜色/形状/边缘等具体证据")
        t = str(f.get("type", ""))
        if t and not t.startswith(("疑似", "可能")) and g != "A":
            warn.append(f"{fid}: 类型“{t}”建议加“疑似”")
    return err, warn
