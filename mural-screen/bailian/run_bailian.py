"""Step ① with 百炼 Qwen-VL instead of Claude: fill 01_findings.json in a case folder made by screen.py.

usage:
  export DASHSCOPE_API_KEY=...
  python run_bailian.py <case> [--model qwen-vl-max] [--use-hints] [--dry-run]
then: python ../scripts/check_findings.py <case>

--dry-run writes 01_bailian_request.json (images shortened) so you can see exactly what would be sent,
without calling the API.
"""
import argparse
import glob
import json
import os
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import caselog  # noqa: E402
import qwen_client as qc  # noqa: E402
from findings_schema import validate  # noqa: E402


def shorten(messages):
    out = json.loads(json.dumps(messages))
    for m in out:
        if isinstance(m["content"], list):
            for p in m["content"]:
                if p.get("type") == "image_url":
                    u = p["image_url"]["url"]
                    p["image_url"]["url"] = u[:60] + f"...({len(u)} chars)"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--model", default=qc.DEFAULT_MODEL)
    ap.add_argument("--base-url", default=qc.DEFAULT_BASE)
    ap.add_argument("--use-hints", action="store_true", help="把 01_hints.json 的小模型提示也告诉模型")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    f = sorted(glob.glob(os.path.join(a.case, "00_input.*")))
    if not f:
        sys.exit("案例里没有 00_input.*，请先运行 scripts/screen.py")
    rgb = cv2.cvtColor(cv2.imread(f[0]), cv2.COLOR_BGR2RGB)
    H, W = rgb.shape[:2]
    hints = (caselog.load(a.case, "01_hints.json", required=False) or {}).get("hints") if a.use_hints else None
    msgs, tile_ids = qc.build_messages(rgb, "skill", hints)

    if a.dry_run:
        caselog.save(a.case, "01_bailian_request.json", {"model": a.model, "messages": shorten(msgs)})
        print("已写出 01_bailian_request.json（未调用百炼）")
        return

    text, usage = qc.call_qwen(msgs, a.model, a.base_url)
    with open(os.path.join(a.case, "01_bailian_raw.txt"), "w", encoding="utf-8") as fo:
        fo.write(text)
    doc = qc.parse_json(text)
    if doc is None:
        sys.exit("模型回复不是合法 JSON，原文见 01_bailian_raw.txt。可以重跑一次。")
    meta = caselog.load(a.case, "case_meta.json")
    doc.update({"image": meta["image_name"], "size_wh": [W, H], "reviewer_model": f"{a.model}（百炼）",
                "manual_version": "mural-screen v2", "tiles_all": tile_ids})
    doc.setdefault("tiles_checked", tile_ids)
    for i, x in enumerate(doc.get("findings") or []):
        x.setdefault("id", f"F{i + 1}")
        x.setdefault("source", "大模型看图")
    caselog.save(a.case, "01_findings.json", doc)
    err, warn = validate(doc, [W, H], strict=True)
    caselog.log(a.case, "① 识别-百炼", f"{a.model}", ["01a_whole", "01b_tiles"], ["01_findings.json", "01_bailian_raw.txt"],
                f"{len(doc.get('findings') or [])} 处，tokens={usage}")
    print(f"已写入 01_findings.json：{len(doc.get('findings') or [])} 处疑似病害")
    for w in warn:
        print("提醒：" + w)
    if err:
        print("格式问题（请人工修改 01_findings.json 后再运行 check_findings.py）：")
        for e in err:
            print("  - " + e)


if __name__ == "__main__":
    main()
