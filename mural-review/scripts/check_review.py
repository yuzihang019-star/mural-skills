"""Step ② (finish): validate 02_review.json and draw 02_regions.png.

usage: python check_review.py <case_dir>
Exit code 1 with a list of problems if the review is incomplete.
"""
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caselog  # noqa: E402

VERDICTS = {"确认", "存疑", "否决"}
CONF = {"高", "中", "低"}
ABSOLUTE = ["确诊", "肯定是", "一定是", "必然", "毫无疑问", "100%"]
COLORS = [(230, 57, 70), (29, 120, 220), (40, 160, 60)]


def main():
    case = sys.argv[1]
    r = caselog.load(case, "02_review.json")
    meta = caselog.load(case, "case_meta.json")
    W, H = meta["size_wh"]
    errs, warns = [], []
    if not r.get("reviewer_model"):
        errs.append("reviewer_model 为空：写明复核所用的视觉模型（来源披露需要）")
    if not r.get("overall_observation"):
        errs.append("overall_observation 为空：写 1–2 句整体观察")
    for c in r.get("candidates", []):
        if c.get("verdict") not in VERDICTS:
            errs.append(f"候选 #{c.get('id')} 的 verdict 须为 确认/存疑/否决")
        if not c.get("evidence"):
            errs.append(f"候选 #{c.get('id')} 缺 evidence（否决也要写原因）")
    regs = r.get("regions", [])
    if not 1 <= len(regs) <= 3:
        errs.append(f"regions 须为 1–3 处，现在 {len(regs)} 处")
    ids = {c["id"] for c in r.get("candidates", [])}
    for g in regs:
        lab = g.get("label", "?")
        for k in ("phenomenon", "type", "evidence", "impact", "confidence"):
            if not g.get(k):
                errs.append(f"区域 {lab} 缺 {k}")
        if g.get("confidence") and g["confidence"] not in CONF:
            errs.append(f"区域 {lab} confidence 须为 高/中/低")
        x, y, w, h = g.get("bbox_xywh", [0, 0, 0, 0])
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > W or y + h > H:
            errs.append(f"区域 {lab} bbox {g.get('bbox_xywh')} 不在图像 {W}x{H} 范围内或为空")
        fc = g.get("from_candidate")
        if fc is not None and fc not in ids:
            errs.append(f"区域 {lab} from_candidate={fc} 不存在")
        g["provenance"] = "AI 生成"
        text = "".join(str(g.get(k, "")) for k in ("phenomenon", "type", "evidence", "impact"))
        for wd in ABSOLUTE:
            if wd in text:
                warns.append(f"区域 {lab} 用了绝对化措辞“{wd}”，图像初判应写“疑似”")
        if g.get("type") and not g["type"].startswith(("疑似", "非病害", "可能")):
            warns.append(f"区域 {lab} 类型“{g['type']}”建议加“疑似”，仅凭图像不能定性")
    if errs:
        print("复核未完成：\n  " + "\n  ".join(errs))
        sys.exit(1)
    caselog.save(case, "02_review.json", r)

    rgb = cv2.imread(caselog.input_image(case))
    s = min(1.0, 1200 / max(H, W))
    vis = cv2.resize(rgb, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    th = max(2, int(max(vis.shape[:2]) / 300))
    for i, g in enumerate(regs):
        x, y, w, h = [int(v * s) for v in g["bbox_xywh"]]
        col = COLORS[i % 3][::-1]
        cv2.rectangle(vis, (x, y), (x + w, y + h), col, th)
        cv2.putText(vis, g["label"], (x + 4, y + 28), cv2.FONT_HERSHEY_SIMPLEX, 1.0, col, th)
    cv2.imwrite(os.path.join(case, "02_regions.png"), vis)

    n = {v: sum(c["verdict"] == v for c in r["candidates"]) for v in VERDICTS}
    added = sum(g.get("from_candidate") is None for g in regs)
    caselog.log(case, "② AI 视觉复核", r["reviewer_model"], ["01_candidates.json", "01_crops.png", "00_input"],
                ["02_review.json", "02_regions.png"],
                f"候选 确认{n['确认']}/存疑{n['存疑']}/否决{n['否决']}；选出 {len(regs)} 处，其中 {added} 处为模型漏检、复核新增")
    print(f"通过。候选：确认 {n['确认']}，存疑 {n['存疑']}，否决 {n['否决']}；最终关注区域 {len(regs)} 处。")
    for w_ in warns:
        print("提醒：" + w_)


if __name__ == "__main__":
    main()
