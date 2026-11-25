"""Validation rules for the unified output format (references/03_输出格式.md). Shared by check_findings.py and the 百炼 eval."""

CONDITIONS = ("好", "一般", "差")
CONF = ("高", "中", "低")
GRADES = ("A", "B", "C")
CATS = ("脱落类", "裂缝类", "结构盐分类", "污染类", "颜色变化类", "人为损害", "其他")
CONF_CAP = {"A": "高", "B": "中", "C": "低"}
CONF_RANK = {"低": 0, "中": 1, "高": 2}


def validate(doc, size_wh=None, strict=True):
    """Return (errors, warnings). strict=False is used for model outputs in the eval (only fatal problems are errors)."""
    err, warn = [], []
    ov = doc.get("overall") or {}
    if strict:
        if not doc.get("reviewer_model"):
            err.append("reviewer_model 未填写")
        if not ov.get("content"):
            err.append("overall.content 未填写（画的是什么）")
        allt = set(doc.get("tiles_all") or [])
        missing = allt - set(doc.get("tiles_checked") or [])
        if missing:
            err.append(f"还有分块没看：{sorted(missing)}")
    if ov.get("condition") not in CONDITIONS:
        (err if strict else warn).append(f"overall.condition 必须是 {CONDITIONS}")
    W, H = size_wh or doc.get("size_wh") or (None, None)
    seen = set()
    for i, f in enumerate(doc.get("findings") or []):
        fid = f.get("id") or f"#{i + 1}"
        if fid in seen:
            err.append(f"{fid}: id 重复")
        seen.add(fid)
        b = f.get("bbox_xywh")
        if not (isinstance(b, (list, tuple)) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b)):
            err.append(f"{fid}: bbox_xywh 必须是 [x,y,w,h] 四个数字")
        else:
            x, y, w, h = b
            if w <= 0 or h <= 0:
                err.append(f"{fid}: 框的宽高必须大于 0")
            if W and H and (x < 0 or y < 0 or x + w > W + 2 or y + h > H + 2):
                err.append(f"{fid}: 框超出图像范围 {W}x{H}")
            if W and H and w * h > 0.6 * W * H:
                warn.append(f"{fid}: 框占了图像 {w * h / (W * H):.0%}，是否框得太大？")
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
            err.append(f"{fid}: {g} 级病害照片无法确认，信心最高只能是“{CONF_CAP[g]}”")
        if g in ("B", "C") and not f.get("how_to_verify"):
            err.append(f"{fid}: {g} 级病害必须写 how_to_verify（怎么去现场核实）")
        if strict and len(str(f.get("evidence", ""))) < 10:
            warn.append(f"{fid}: evidence 太短，请写出颜色/形状/边缘等具体证据")
        t = str(f.get("type", ""))
        if t and not t.startswith(("疑似", "可能")) and g != "A":
            warn.append(f"{fid}: 类型“{t}”建议加“疑似”")
    return err, warn
