"""Step ② (start): write a 02_review.json template from the step-① candidates.

usage: python init_review.py <case_dir> [--model "复核所用视觉模型名称"] [--force]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caselog  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case"); ap.add_argument("--model", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if os.path.exists(os.path.join(a.case, "02_review.json")) and not a.force:
        sys.exit("02_review.json 已存在；要重建请加 --force")
    c = caselog.load(a.case, "01_candidates.json")
    tpl = {
        "reviewer_model": a.model,
        "overall_observation": "",
        "candidates": [{"id": d["id"], "bbox_xywh": d["bbox_xywh"], "model_hint": d["type_hint"],
                        "verdict": "", "type": "", "evidence": "", "confidence": ""}
                       for d in c["candidates"]],
        "regions": [{"label": "A", "from_candidate": None, "bbox_xywh": [0, 0, 0, 0],
                     "phenomenon": "", "type": "", "evidence": "", "impact": "",
                     "confidence": "", "needs_onsite": "", "provenance": "AI 生成"}],
    }
    caselog.save(a.case, "02_review.json", tpl)
    print(f"已生成模板 {os.path.join(a.case, '02_review.json')}，含 {len(tpl['candidates'])} 个候选待复核")


if __name__ == "__main__":
    main()
