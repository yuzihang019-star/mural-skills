"""Step ② (start): write a 03_conservation.json template from 02_review.json.

usage: python init_conservation.py <case_dir> [--model "模型名称"] [--force]
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
    if os.path.exists(os.path.join(a.case, "03_conservation.json")) and not a.force:
        sys.exit("03_conservation.json 已存在；要重建请加 --force")
    r = caselog.load(a.case, "02_review.json")
    tpl = {
        "advisor_model": a.model or r.get("reviewer_model", ""),
        "object_context": None,
        "overall_strategy": None,
        "suggestions": None,
        "uncertainty": None,
        "human_check_points": None,
        "references": [],
    }
    caselog.save(a.case, "03_conservation.json", tpl)
    print("已生成模板 03_conservation.json。可引用的区域：")
    photo_support = {"高": "较清楚", "中": "有限", "低": "较弱"}
    for g in r["regions"]:
        d = g.get("diagnosis") or {}
        support = photo_support.get(d.get("confidence") or g.get("confidence"), "未记录")
        print(f"  {g['label']}  {d.get('primary') or g.get('type')}"
              f"（照片依据 {support}，人工核查 {d.get('priority', '未定')}）")
    if not r["regions"]:
        print("  无（可只写整体保护思路与整体性建议）")


if __name__ == "__main__":
    main()
