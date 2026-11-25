"""Step ③ (finish): validate 03_advice.json.

usage: python check_advice.py <case_dir>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caselog  # noqa: E402

CATS = {"保护", "数字展示", "公众传播"}
RISKY = {"恢复原貌": "虚拟修复只能给出候选方案，不能声称恢复原貌",
         "还原真实": "同上，改为“提供参考性复原方案”",
         "修复施工": "比赛不涉及实体修复施工，建议只写数字层面",
         "直接修补": "实体干预须由专业人员决定，不应由 AI 建议",
         "确诊": "图像初判不能确诊", "一定": "避免绝对化", "必然": "避免绝对化"}


def main():
    case = sys.argv[1]
    a = caselog.load(case, "03_advice.json")
    r = caselog.load(case, "02_review.json")
    labels = {g["label"] for g in r["regions"]}
    errs, warns = [], []
    if not a.get("advisor_model"):
        errs.append("advisor_model 为空")
    sg = a.get("suggestions", [])
    if not 1 <= len(sg) <= 2:
        errs.append(f"suggestions 须为 1–2 条，现在 {len(sg)} 条")
    for s in sg:
        n = s.get("no", "?")
        if s.get("category") not in CATS:
            errs.append(f"建议 {n} category 须为 保护/数字展示/公众传播")
        for k in ("title", "content", "basis", "risk"):
            if not s.get(k):
                errs.append(f"建议 {n} 缺 {k}")
        bad = [x for x in s.get("related_regions", []) if x not in labels]
        if bad:
            errs.append(f"建议 {n} 引用了不存在的区域 {bad}")
        if not s.get("related_regions"):
            warns.append(f"建议 {n} 没有关联任何区域，依据可能不够具体")
        s["provenance"] = "AI 生成"
        text = "".join(str(s.get(k, "")) for k in ("title", "content", "basis"))
        for w, why in RISKY.items():
            if w in text:
                warns.append(f"建议 {n} 含“{w}”：{why}")
    if len({s.get("category") for s in sg}) < len(sg):
        warns.append("两条建议类型相同，换成不同方向（如一条保护、一条数字展示）信息量更大")
    if not [u for u in a.get("uncertainty", []) if u]:
        errs.append("uncertainty 至少写 1 条")
    if not [u for u in a.get("human_check_points", []) if u]:
        errs.append("human_check_points 至少写 1 条")
    for ref in a.get("references", []):
        if not ref.get("name"):
            errs.append("references 中有条目缺 name")
    if errs:
        print("建议未完成：\n  " + "\n  ".join(errs))
        sys.exit(1)
    caselog.save(case, "03_advice.json", a)
    caselog.log(case, "③ 建议与风险", a["advisor_model"], ["02_review.json"], ["03_advice.json"],
                f"{len(sg)} 条建议（{'、'.join(s['category'] for s in sg)}）；"
                f"{len(a['uncertainty'])} 条不确定性，{len(a['human_check_points'])} 个人工复核点")
    print(f"通过：{len(sg)} 条建议。")
    for w in warns:
        print("提醒：" + w)


if __name__ == "__main__":
    main()
