"""Step ② (finish): validate 03_conservation.json.

usage: python check_conservation.py <case_dir>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caselog  # noqa: E402

CATS = {"保护", "数字展示", "公众传播"}
STAGES = {"调查诊断", "预防性保护", "应急稳定", "修复处理", "监测"}
URGENCY = {"紧急", "优先", "常规", "随访"}
INTERVENTION = {"应急稳定", "修复处理"}
RISKY = {
    "恢复原貌": "数字复原请交代推测依据、证据不足的部分和展示标识",
    "还原真实": "核对措辞是否许诺了影像证据无法支持的结果",
    "补绘": "实物上不补绘画面内容；缺失部分只做数字示意",
    "重绘": "实物上不重绘；缺失部分只做数字示意",
    "确诊": "核对影像证据能支持的判断层级",
    "立即施工": "实体处理须先经现场调查、试验和审批",
}
# 本 skill 只写措施方向，不写配方与工艺参数
RECIPE = re.compile(r"\d+(\.\d+)?\s*(%|％|wt|mg|ml|mL|g/|克|毫升|比\s*\d)|配比|浓度为|按\s*\d+\s*[:：]\s*\d+")
EXPERT = ("专业", "文保", "现场", "试验", "审批")


def main():
    case = sys.argv[1]
    a = caselog.load(case, "03_conservation.json")
    r = caselog.load(case, "02_review.json")
    regions = {g["label"]: g for g in r["regions"]}
    errs, warns = [], []
    if not a.get("advisor_model"):
        errs.append("advisor_model 为空")
    for field in ("object_context", "overall_strategy"):
        if not isinstance(a.get(field), str) or not a[field].strip():
            errs.append(f"{field} 须为非空文本（未知信息写“未提供”）")
    for field in ("suggestions", "uncertainty", "human_check_points", "references"):
        if not isinstance(a.get(field), list):
            errs.append(f"{field} 须为数组，无条目时写 []")
    if errs:
        sys.exit("保护建议未完成：\n  " + "\n  ".join(errs))
    sg = a["suggestions"]
    numbers, covered = set(), set()
    for s in sg:
        n = s.get("no", "?")
        if type(n) is not int or n < 1:
            errs.append(f"建议编号 {n!r} 须为正整数")
        elif n in numbers:
            errs.append(f"建议编号 {n} 重复")
        else:
            numbers.add(n)
        cat = s.get("category")
        if cat not in CATS:
            errs.append(f"建议 {n} category 须为 保护/数字展示/公众传播")
        if cat == "保护":
            if s.get("stage") not in STAGES:
                errs.append(f"建议 {n} stage 须为 {'/'.join(sorted(STAGES))}")
            if not isinstance(s.get("preconditions"), str) or not s["preconditions"].strip():
                errs.append(f"建议 {n} 缺 preconditions（实施前提或触发条件）")
        if s.get("urgency") not in URGENCY:
            errs.append(f"建议 {n} urgency 须为 紧急/优先/常规/随访")
        for k in ("title", "content", "basis", "risk"):
            if not isinstance(s.get(k), str) or not s[k].strip():
                errs.append(f"建议 {n} 缺 {k}")
        related = s.get("related_regions", [])
        if not isinstance(related, list) or not all(isinstance(label, str) for label in related):
            errs.append(f"建议 {n} 的 related_regions 须为区域标签数组")
        else:
            bad = [label for label in related if label not in regions]
            if bad:
                errs.append(f"建议 {n} 引用了不存在的区域 {bad}")
            covered |= set(related)
        s["provenance"] = "AI 生成"
        text = "".join(str(s.get(k, "")) for k in ("title", "content", "basis", "preconditions"))
        for w, why in RISKY.items():
            if w in text:
                warns.append(f"建议 {n} 含“{w}”：{why}")
        if RECIPE.search(text):
            warns.append(f"建议 {n} 似乎写了配比、浓度或用量：本 skill 只写措施方向，参数由专业人员经试验确定")
        if s.get("stage") in INTERVENTION and not any(k in str(s.get("preconditions", "")) for k in EXPERT):
            warns.append(f"建议 {n} 属于{s['stage']}，请在 preconditions 写明由专业人员经现场评估或试验后决定")
    for lab, g in regions.items():
        if lab not in covered:
            pri = (g.get("diagnosis") or {}).get("priority")
            msg = f"区域 {lab} 没有任何建议引用"
            (warns.append(msg + "（该区核查优先级为“优先”，请确认是否遗漏）") if pri == "优先"
             else warns.append(msg + "；若只需记录，可在整体保护思路中说明"))
    for field in ("uncertainty", "human_check_points"):
        if any(not isinstance(entry, str) or not entry.strip() for entry in a[field]):
            errs.append(f"{field} 包含空白或非文本条目，无条目时写 []")
    for ref in a["references"]:
        if not ref.get("name"):
            errs.append("references 中有条目缺 name")
    if errs:
        print("保护建议未完成：\n  " + "\n  ".join(errs))
        sys.exit(1)
    caselog.save(case, "03_conservation.json", a)
    stages = "、".join(s.get("stage") or s["category"] for s in sg)
    caselog.log(case, "② 病害保护建议", a["advisor_model"], ["02_review.json"], ["03_conservation.json"],
                f"{len(sg)} 条建议（{stages}）；{len(a['uncertainty'])} 条不确定性，"
                f"{len(a['human_check_points'])} 个人工复核点")
    print(f"通过：{len(sg)} 条建议，覆盖区域 {', '.join(sorted(covered)) or '无'}。")
    for w in warns:
        print("提醒：" + w)
    print("下一步：mural-review-pdf 生成人工复核 PDF。")


if __name__ == "__main__":
    main()
