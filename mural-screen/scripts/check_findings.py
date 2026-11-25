"""Step ① (finish): validate 01_findings.json, draw it, and hand it to step ②.

usage: python check_findings.py <case>

On success writes 01_findings.png (boxes F1..Fn), 01_candidates.json + 01_crops.png (the files ② mural-review reads),
and appends to workflow_log.jsonl. On failure prints what to fix and writes nothing else.
"""
import glob
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

    rgb = cv2.cvtColor(cv2.imread(sorted(glob.glob(os.path.join(case, "00_input.*")))[0]), cv2.COLOR_BGR2RGB)
    F = doc["findings"]
    boxes = [tuple(int(v) for v in f["bbox_xywh"]) for f in F]
    views.save(os.path.join(case, "01_findings.png"), views.draw_boxes(rgb, boxes, [f["id"] for f in F]))
    views.save(os.path.join(case, "01_crops.png"), views.zoom(rgb, boxes, [f"#{i + 1} {f['id']}" for i, f in enumerate(F)]))
    hints = caselog.load(case, "01_hints.json", required=False)
    caselog.save(case, "01_candidates.json", {
        "image": doc["image"], "size_wh": meta["size_wh"],
        "model": f"{doc['reviewer_model']} 按 mural-screen v2 识别手册看图（病害百科 + 分块看图 + 检查表）",
        "model_note": "大模型识别结果，均为“疑似”，需经 ② 复核、④ 人工确认",
        "overall": doc["overall"],
        "small_model_hints_used": bool(hints),
        "candidates": [{"id": i + 1, "finding_id": f["id"], "bbox_xywh": [int(v) for v in f["bbox_xywh"]],
                        "type_hint": f["type"], "category": f.get("category"), "photo_grade": f.get("photo_grade"),
                        "confidence": f["confidence"], "evidence": f["evidence"],
                        "how_to_verify": f.get("how_to_verify", ""), "source": f.get("source", ""),
                        "mean_prob": None} for i, f in enumerate(F)],
        "rejected": doc.get("rejected", [])})
    caselog.log(case, "① 病害识别", doc["reviewer_model"] + "（按识别手册）", ["00_input", "01a_whole.png", "01b_tiles.png"],
                ["01_findings.json", "01_findings.png", "01_candidates.json", "01_crops.png"],
                f"{len(F)} 处疑似病害，排除 {len(doc.get('rejected', []))} 处误报")
    print(f"通过：{len(F)} 处疑似病害，排除 {len(doc.get('rejected', []))} 处。已生成 01_findings.png、01_candidates.json。")
    print("下一步：② mural-review")


if __name__ == "__main__":
    main()
