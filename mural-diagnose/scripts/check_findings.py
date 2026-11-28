"""Step ① (finish): validate 01_findings.json, draw it, and hand it to stage 2 (review).

usage: python check_findings.py <case>

On success writes 01_findings.png (boxes F1..Fn), 01_candidates.json + 01_crops.png (read by stage 2, init_review.py),
and appends to workflow_log.jsonl. On failure prints what to fix and writes nothing else.
"""
import glob
import math
import os
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import caselog  # noqa: E402
import views  # noqa: E402
from findings_schema import validate  # noqa: E402


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    case = sys.argv[1]
    doc = caselog.load(case, "01_findings.json")
    meta = caselog.load(case, "case_meta.json")
    err, warn = validate(doc, meta["size_wh"], strict=True)
    for w in warn:
        print("提醒：" + w)
    if err:
        print("未通过，请修改 01_findings.json：")
        for e in err:
            print("  - " + e)
        sys.exit(1)

    inputs = glob.glob(os.path.join(case, "00_input.*"))
    if len(inputs) != 1:
        sys.exit("案例须包含唯一的 00_input 基准照片")
    image = cv2.imread(inputs[0])
    if image is None or list(image.shape[:2][::-1]) != meta["size_wh"]:
        sys.exit("基准照片无法读取或尺寸与 case_meta.json 不符")
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    F = doc["findings"]
    boxes = []
    for finding in F:
        x, y, width, height = finding["bbox_xywh"]
        left, top = math.floor(x), math.floor(y)
        boxes.append((left, top, math.ceil(x + width) - left, math.ceil(y + height) - top))
    views.save(os.path.join(case, "01_findings.png"), views.draw_boxes(rgb, boxes, [f["id"] for f in F]))
    views.save(os.path.join(case, "01_crops.png"), views.zoom(rgb, boxes, [f"#{i + 1} {f['id']}" for i, f in enumerate(F)]))
    hints_used = doc.get("small_model_hints_used")
    if hints_used is None and any("小模型提示" in f.get("source", "") for f in F):
        hints_used = True
    caselog.save(case, "01_candidates.json", {
        "image": doc["image"], "size_wh": meta["size_wh"],
        "model": f"{doc['reviewer_model']} · {doc.get('manual_version') or 'mural-diagnose'} 图像初筛",
        "model_note": "记录限于当前基准影像与判读范围，待视觉复核及人工确认",
        "overall": doc["overall"],
        "small_model_hints_used": hints_used,
        "candidates": [{"id": i + 1, "finding_id": f["id"], "bbox_xywh": list(box),
                        "type_hint": f["type"], "category": f.get("category"), "photo_grade": f.get("photo_grade"),
                        "confidence": f["confidence"], "evidence": f["evidence"], "alternatives": f.get("alternatives", ""),
                        "how_to_verify": f.get("how_to_verify", ""), "source": f.get("source", ""),
                        "mean_prob": None} for i, (f, box) in enumerate(zip(F, boxes))],
        "rejected": doc.get("rejected", [])})
    caselog.log(case, "①-1 病害初筛", doc["reviewer_model"] + "（按识别手册）", ["00_input", "01a_whole.png", "01b_tiles.png"],
                ["01_findings.json", "01_findings.png", "01_candidates.json", "01_crops.png"],
                f"{len(F)} 处疑似病害，排除 {len(doc.get('rejected', []))} 处误报")
    print(f"通过：{len(F)} 处疑似病害，排除 {len(doc.get('rejected', []))} 处。已生成 01_findings.png、01_candidates.json。")
    print("下一步：第二阶段逐条复核，运行 init_review.py")


if __name__ == "__main__":
    main()
