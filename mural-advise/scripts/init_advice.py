"""Step ③ (start): write a 03_advice.json template.

usage: python init_advice.py <case_dir> [--model "模型名称"] [--force]
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
    if os.path.exists(os.path.join(a.case, "03_advice.json")) and not a.force:
        sys.exit("03_advice.json 已存在；要重建请加 --force")
    r = caselog.load(a.case, "02_review.json")
    labels = [g["label"] for g in r["regions"]]
    tpl = {
        "advisor_model": a.model or r.get("reviewer_model", ""),
        "suggestions": [{"no": 1, "category": "", "title": "", "content": "", "basis": "",
                         "related_regions": labels[:1], "risk": "", "provenance": "AI 生成"}],
        "uncertainty": [""],
        "human_check_points": [""],
        "references": [],
    }
    caselog.save(a.case, "03_advice.json", tpl)
    print(f"已生成模板，可引用的区域：{', '.join(labels)}")


if __name__ == "__main__":
    main()
