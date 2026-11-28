"""Stage 2 (finish): validate 02_review.json and draw 02_regions.png.

usage: python check_review.py <case_dir>
Exit code 1 with a list of problems if the review is incomplete.
"""
from math import hypot
import os
import re
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caselog  # noqa: E402

VERDICTS = {"确认", "存疑", "否决"}
CONF = {"高", "中", "低"}
DIAGNOSIS_TEXT = ("primary", "reason", "alternative", "verification")
PRIORITIES = {"优先", "常规", "随访"}
ABSOLUTE = ["确诊", "肯定是", "一定是", "必然", "毫无疑问", "100%"]
COLORS = [(230, 57, 70), (29, 120, 220), (40, 160, 60)]


def valid_box(box, width, height):
    if not (isinstance(box, list) and len(box) == 4):
        return False
    if not all(type(value) is int for value in box):
        return False
    x, y, w, h = box
    return 0 <= x < width and 0 <= y < height and 0 < w <= width - x and 0 < h <= height - y


def draw_mark(vis, mark, scale, color, thickness):
    max_y, max_x = (v - 1 for v in vis.shape[:2])
    points = [(min(max_x, int(x * scale)), min(max_y, int(y * scale))) for x, y in mark["points"]]
    tentative = mark.get("tentative", False)
    kind = mark["kind"]
    if kind == "point":
        cv2.circle(vis, points[0], thickness + 2, color, thickness if tentative else -1, cv2.LINE_AA)
        return
    tail = points[1:] if kind == "line" else points[1:] + points[:1]
    for start, end in zip(points, tail):
        if not tentative:
            cv2.line(vis, start, end, color, thickness, cv2.LINE_AA)
            continue
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = max(1, round(hypot(dx, dy)))
        dash = thickness * 3
        for offset in range(0, length, dash * 2):
            tip = min(length, offset + dash)
            a = (start[0] + round(dx * offset / length), start[1] + round(dy * offset / length))
            b = (start[0] + round(dx * tip / length), start[1] + round(dy * tip / length))
            cv2.line(vis, a, b, color, thickness, cv2.LINE_AA)


def main():
    case = sys.argv[1]
    r = caselog.load(case, "02_review.json")
    meta = caselog.load(case, "case_meta.json")
    W, H = meta["size_wh"]
    errs, warns = [], []
    if not r.get("reviewer_model"):
        errs.append("reviewer_model 为空：写明复核所用的视觉模型（来源披露需要）")
    if not str(r.get("overall_observation") or "").strip():
        errs.append("overall_observation 为空：交代影像覆盖范围、可见状况和影响判断的限制")
    source = caselog.load(case, "01_candidates.json")
    source_candidates = {c["id"]: c for c in source["candidates"]}
    candidates = r.get("candidates")
    regs = r.get("regions")
    if not isinstance(candidates, list) or not isinstance(regs, list):
        sys.exit("candidates 和 regions 须为数组，无记录时写 []")
    verdicts = {}
    for c in candidates:
        candidate_id = c.get("id")
        if candidate_id not in source_candidates:
            errs.append(f"候选 #{candidate_id} 不在 01_candidates.json 中")
        elif c.get("bbox_xywh") != source_candidates[candidate_id]["bbox_xywh"]:
            errs.append(f"候选 #{candidate_id} 的坐标与初筛不同；可在 regions 中细化范围")
        if candidate_id in verdicts:
            errs.append(f"候选 #{candidate_id} 的复核记录重复")
        verdicts[candidate_id] = c.get("verdict")
        if verdicts[candidate_id] not in VERDICTS:
            errs.append(f"候选 #{candidate_id} 的 verdict 须为 确认/存疑/否决")
        if not str(c.get("evidence") or "").strip():
            errs.append(f"候选 #{candidate_id} 缺 evidence（含否决依据）")
        if c.get("confidence") and c["confidence"] not in CONF:
            errs.append(f"候选 #{candidate_id} 的 confidence 须为 高/中/低")
    missing = [str(candidate_id) for candidate_id in source_candidates if candidate_id not in verdicts]
    if missing:
        errs.append(f"以下初筛候选尚未复核：{', '.join(missing)}")
    region_labels = set()
    for g in regs:
        lab = g.get("label", "?")
        if not isinstance(lab, str) or not re.fullmatch(r"[A-Z]+", lab):
            errs.append(f"区域标签 {lab!r} 须用大写拉丁字母（如 A、Z、AA）")
        elif lab in region_labels:
            errs.append(f"区域标签 {lab} 重复")
        else:
            region_labels.add(lab)
        for k in ("phenomenon", "type", "evidence", "impact", "confidence"):
            if not str(g.get(k) or "").strip():
                errs.append(f"区域 {lab} 缺 {k}")
        if g.get("confidence") and g["confidence"] not in CONF:
            errs.append(f"区域 {lab} confidence 须为 高/中/低")
        if "diagnosis" in g:
            diagnosis = g["diagnosis"]
            if not isinstance(diagnosis, dict):
                errs.append(f"区域 {lab} 的 diagnosis 须为对象")
            else:
                for key in DIAGNOSIS_TEXT:
                    if not isinstance(diagnosis.get(key), str) or not diagnosis[key].strip():
                        errs.append(f"区域 {lab} 的 diagnosis 缺 {key}")
                if diagnosis.get("confidence") not in CONF:
                    errs.append(f"区域 {lab} 的诊断置信度须为 高/中/低")
                if diagnosis.get("priority") not in PRIORITIES:
                    errs.append(f"区域 {lab} 的核查优先级须为 优先/常规/随访")
        else:
            warns.append(f"区域 {lab} 没有 diagnosis。旧记录仍可读取，新记录请分开写病害判断与人工核查方法")
        box = g.get("bbox_xywh")
        if not valid_box(box, W, H):
            errs.append(f"区域 {lab} bbox 须为图像 {W}x{H} 范围内的整数像素框，当前 {g.get('bbox_xywh')}")
        elif "map_marks" in g:
            errs.extend(f"区域 {lab} 的 {error}" for error in caselog.map_marks_errors(g["map_marks"], box))
        fc = g.get("from_candidate")
        if fc is not None:
            if fc not in verdicts:
                errs.append(f"区域 {lab} from_candidate={fc} 不存在")
            elif verdicts[fc] == "否决":
                errs.append(f"区域 {lab} 引用了已否决的候选 #{fc}；若有独立现象，请作为新增区域记录")
        g["provenance"] = "AI 生成"
        text_fields = [g.get(k, "") for k in ("phenomenon", "type", "evidence", "impact")]
        if isinstance(g.get("diagnosis"), dict):
            text_fields.extend(g["diagnosis"].get(k, "") for k in ("primary", "reason"))
        text = " ".join(map(str, text_fields))
        for wd in ABSOLUTE:
            if wd in text:
                warns.append(f"区域 {lab} 用了绝对化措辞“{wd}”，请核对措辞是否超出影像证据")
    if errs:
        print("复核未完成：\n  " + "\n  ".join(errs))
        sys.exit(1)
    rgb = cv2.imread(caselog.input_image(case))
    if rgb is None or rgb.shape[:2] != (H, W):
        sys.exit("无法读取原图，或原图尺寸与 case_meta.json 记录不符")
    s = min(1.0, 1200 / max(H, W))
    vis = cv2.resize(rgb, (max(1, int(W * s)), max(1, int(H * s))), interpolation=cv2.INTER_AREA)
    th = max(2, int(max(vis.shape[:2]) / 300))
    for i, g in enumerate(regs):
        x, y, w, h = g["bbox_xywh"]
        left = min(vis.shape[1] - 1, int(x * s))
        top = min(vis.shape[0] - 1, int(y * s))
        right = min(vis.shape[1] - 1, int((x + w) * s))
        bottom = min(vis.shape[0] - 1, int((y + h) * s))
        col = COLORS[i % len(COLORS)][::-1]
        if g.get("map_marks"):
            for mark in g["map_marks"]:
                draw_mark(vis, mark, s, col, th)
        else:
            cv2.rectangle(vis, (left, top), (right, bottom), col, th)
        font = cv2.FONT_HERSHEY_SIMPLEX
        (text_width, text_height), _ = cv2.getTextSize(g["label"], font, 0.8, th)
        text_x = max(0, min(left + 4, vis.shape[1] - text_width - 2))
        text_y = min(vis.shape[0] - 1, max(text_height, top + text_height + 4))
        cv2.putText(vis, g["label"], (text_x, text_y), font, 0.8, col, th)
    if not cv2.imwrite(os.path.join(case, "02_regions.png"), vis):
        sys.exit("02_regions.png 写入失败")
    caselog.save(case, "02_review.json", r)

    n = {v: sum(c["verdict"] == v for c in candidates) for v in VERDICTS}
    added = sum(g.get("from_candidate") is None for g in regs)
    caselog.log(case, "①-2 病害复核", r["reviewer_model"], ["01_candidates.json", "01_crops.png", "00_input"],
                ["02_review.json", "02_regions.png"],
                f"候选 确认{n['确认']}/存疑{n['存疑']}/否决{n['否决']}；关注区域 {len(regs)} 处，其中 {added} 处复核新增")
    print(f"通过。候选：确认 {n['确认']}，存疑 {n['存疑']}，否决 {n['否决']}；复核关注区域 {len(regs)} 处。")
    print("病害识别分析完成。下一步：mural-conserve 编制保护建议。")
    for w_ in warns:
        print("提醒：" + w_)


if __name__ == "__main__":
    main()
