"""Does the skill make Qwen-VL better? Run the same test images with and without the manual, score against labels.

usage:
  export DASHSCOPE_API_KEY=...
  python eval_bailian.py <MuralDH/Mural_seg> <out_dir> --limit 40 [--model qwen-vl-max] [--modes baseline,skill,skill_hints]
  python eval_bailian.py <Mural_seg> <out_dir> --limit 5 --mock      # no API: checks the pipeline only

Modes:  baseline    = plain image + output format only (no skill)
        skill       = manual + whole/tile views
        skill_hints = skill + small-model hints
Replies are cached in <out_dir>/raw/<mode>/<image>.txt, so an interrupted run can be resumed.
Scoring (same rule as scripts/evaluate.py): a box "hits" when >= 10% of its pixels are labelled damage;
random baseline = same box sizes placed at random. NOTE: labels only mark loss/exposed-ground damage,
so cracks/stains the model correctly reports can count as "misses" — compare modes, not absolute numbers.
Writes summary.json and 对比结果.md (plain language).
"""
import argparse
import json
import os
import random
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import qwen_client as qc  # noqa: E402
from findings_schema import validate  # noqa: E402

DAMAGED, CLEAN = 0.02, 0.005


def boxes_of(doc, W, H):
    out = []
    for f in (doc or {}).get("findings") or []:
        b = f.get("bbox_xywh")
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b)):
            continue
        x, y, w, h = [int(round(v)) for v in b]
        x, y = max(0, min(W - 1, x)), max(0, min(H - 1, y))
        w, h = max(1, min(W - x, w)), max(1, min(H - y, h))
        out.append((x, y, w, h))
    return out


def mock_reply(mode, rgb, hints, rng):
    H, W = rgb.shape[:2]
    if mode == "baseline":
        bx = [[rng.randrange(0, W - 60), rng.randrange(0, H - 60), 60, 60]]
    else:
        bx = [h["bbox_xywh"] for h in (hints or [])][:3]
    return json.dumps({"overall": {"content": "mock", "condition": "一般"}, "findings": [
        {"id": f"F{i+1}", "bbox_xywh": b, "type": "疑似颜料层脱落", "category": "脱落类", "photo_grade": "A",
         "evidence": "mock evidence text here", "confidence": "中", "alternatives": "-"} for i, b in enumerate(bx)]},
        ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seg"); ap.add_argument("out")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--modes", default="baseline,skill")
    ap.add_argument("--model", default=qc.DEFAULT_MODEL)
    ap.add_argument("--base-url", default=qc.DEFAULT_BASE)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    modes = [m.strip() for m in a.modes.split(",") if m.strip()]
    names = sorted(os.listdir(os.path.join(a.seg, "test", "images")))
    random.Random(a.seed).shuffle(names)
    names = names[:a.limit]
    need_hints = any(m == "skill_hints" for m in modes) or a.mock
    if need_hints:
        from detect import candidates
        from model import PixelMLP
        mlp = PixelMLP.load(os.path.join(os.path.dirname(HERE), "model", "pixel_mlp.npz"))

    rng = random.Random(a.seed)
    nprng = np.random.default_rng(a.seed)
    S = {m: dict(n=0, valid=0, nfind=0, nbox=0, hits=0, rand=0.0, dmg_imgs=0, dmg_found=0,
                 clean_imgs=0, clean_quiet=0, rule_err=0) for m in modes}
    for k, nm in enumerate(names):
        rgb = cv2.cvtColor(cv2.imread(os.path.join(a.seg, "test", "images", nm)), cv2.COLOR_BGR2RGB)
        gt = cv2.imread(os.path.join(a.seg, "test", "labels", nm), 0) > 127
        H, W = gt.shape
        frac = gt.mean()
        hints = None
        if need_hints:
            cs, *_ = candidates(mlp, rgb, 5)
            hints = [{"bbox_xywh": c["bbox_xywh"]} for c in cs]
        for m in modes:
            cache = os.path.join(a.out, "raw" + ("_mock" if a.mock else ""), m, os.path.splitext(nm)[0] + ".txt")
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            if os.path.exists(cache):
                text = open(cache, encoding="utf-8").read()
            else:
                if a.mock:
                    text = mock_reply(m, rgb, hints, rng)
                else:
                    msgs, _ = qc.build_messages(rgb, "baseline" if m == "baseline" else "skill",
                                                hints if m == "skill_hints" else None)
                    text, _ = qc.call_qwen(msgs, a.model, a.base_url)
                with open(cache, "w", encoding="utf-8") as fo:
                    fo.write(text)
            doc = qc.parse_json(text)
            s = S[m]; s["n"] += 1
            if doc is None:
                continue
            s["valid"] += 1
            err, _ = validate(doc, [W, H], strict=False)
            s["rule_err"] += len(err)
            bx = boxes_of(doc, W, H)
            s["nfind"] += len(bx)
            hit_any = False
            for x, y, w, h in bx:
                d = gt[y:y + h, x:x + w].mean()
                s["nbox"] += 1; s["hits"] += d >= 0.10; hit_any |= d >= 0.10
                for _ in range(10):
                    rx, ry = int(nprng.integers(0, W - w + 1)), int(nprng.integers(0, H - h + 1))
                    s["rand"] += (gt[ry:ry + h, rx:rx + w].mean() >= 0.10) / 10
            if frac >= DAMAGED:
                s["dmg_imgs"] += 1; s["dmg_found"] += hit_any
            elif frac < CLEAN:
                s["clean_imgs"] += 1; s["clean_quiet"] += len(bx) == 0
        print(f"[{k + 1}/{len(names)}] {nm}", flush=True)

    summ = {}
    for m, s in S.items():
        r = lambda a_, b_: round(a_ / b_, 3) if b_ else None  # noqa: E731
        summ[m] = {"images": s["n"], "valid_json_rate": r(s["valid"], s["n"]),
                   "findings_per_image": r(s["nfind"], s["valid"]),
                   "box_hit_rate": r(s["hits"], s["nbox"]), "random_box_hit_rate": r(s["rand"], s["nbox"]),
                   "damaged_images_found_rate": r(s["dmg_found"], s["dmg_imgs"]), "damaged_images": s["dmg_imgs"],
                   "clean_images_no_report_rate": r(s["clean_quiet"], s["clean_imgs"]), "clean_images": s["clean_imgs"],
                   "rule_errors_per_image": r(s["rule_err"], s["valid"])}
    summ["_settings"] = {"model": "MOCK" if a.mock else a.model, "limit": a.limit, "seed": a.seed}
    os.makedirs(a.out, exist_ok=True)
    json.dump(summ, open(os.path.join(a.out, "summary.json"), "w"), ensure_ascii=False, indent=1)

    def ten(x):
        return "—" if x is None else f"10 次里约 {x * 10:.1f} 次"
    L = [f"# 有无识别手册的对比（{summ['_settings']['model']}，测试图 {len(names)} 张）", "",
         "| 指标 | " + " | ".join(modes) + " |", "|---|" + "---|" * len(modes)]
    rows = [("回复能按格式解析", "valid_json_rate"), ("平均每张报几处", "findings_per_image"),
            ("报出的框落在真实脱落上", "box_hit_rate"), ("（同样大小随机框）", "random_box_hit_rate"),
            ("有明显脱落的图，至少找对一处", "damaged_images_found_rate"),
            ("基本没病害的图，没有乱报", "clean_images_no_report_rate"), ("每张违反规则次数", "rule_errors_per_image")]
    for lab, key in rows:
        vals = [summ[m][key] for m in modes]
        L.append(f"| {lab} | " + " | ".join(str(v) if key in ("findings_per_image", "rule_errors_per_image")
                                              else ten(v) for v in vals) + " |")
    L += ["", "说明：数据集只标了“脱落/露底”，模型正确报出的裂缝、污渍也会被算成“没落在真实脱落上”，"
          "所以重点看几种方式之间的差别，不要把数字当成绝对准确率。"]
    open(os.path.join(a.out, "对比结果.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
