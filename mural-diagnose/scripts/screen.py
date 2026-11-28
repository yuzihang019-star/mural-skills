"""Step ① (prepare): create the case folder and all the images the vision model needs to look carefully.

usage: python screen.py <image> <case_dir> [--source "图片来源"] [--team "队名"] [--no-hints]

Writes:
  00_input.*, case_meta.json
  01a_whole.png     whole image + coordinate grid + tile ids      (look step 1)
  01b_tiles.png     every tile enlarged                            (look step 2)
  01c_enhanced.png  contrast-enhanced whole image                  (look step 2, optional)
  01_hints.json/.png  offline small-model "maybe loss here" hints  (look step 5, optional)
  01_findings.json  empty template in the unified output format
and appends to workflow_log.jsonl. The vision model then fills 01_findings.json and runs check_findings.py.
"""
import argparse
import filecmp
import glob
import json
import os
import shutil
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import caselog  # noqa: E402
import views  # noqa: E402


def run_hints(rgb, case, top, weights):
    from detect import candidates, overlay
    from model import PixelMLP
    m = PixelMLP.load(weights)
    cands, pm, scale, frac = candidates(m, rgb, top)
    mp = os.path.join(os.path.dirname(weights), "test_metrics.json")
    metrics = json.load(open(mp)) if os.path.exists(mp) else {}
    caselog.save(case, "01_hints.json", {
        "what": "离线小模型提示（只认脱落/露底类，约四分之三提示不在真实病害上），仅供大模型回看，不是结论",
        "model": "PixelMLP 像素分类器（NumPy，自训练于 MuralDH Mural_seg/train 760 张，CC0）",
        "model_test_metrics": {k: metrics.get(k) for k in ("pixel_f1", "top3_box_hit_rate", "random_box_hit_rate",
                                                           "hit_rate_lift") if k in metrics},
        "flagged_area_frac": round(frac, 4),
        "hints": [{"id": f"H{c['id']}", "bbox_xywh": c["bbox_xywh"], "mean_prob": c["mean_prob"],
                   "shape_hint": c["type_hint"]} for c in cands]})
    overlay(rgb, pm, scale, cands, os.path.join(case, "01_hints.png"))
    return len(cands), frac


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image"); ap.add_argument("case")
    ap.add_argument("--source", default="", help="图片来源（如：项目照片、档案编号或数据集及许可）")
    ap.add_argument("--team", default="", help="机构或项目（沿用 team 元数据字段）")
    ap.add_argument("--no-hints", action="store_true", help="不运行小模型")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--weights", default=os.path.join(HERE, "..", "model", "pixel_mlp.npz"))
    a = ap.parse_args()

    bgr = cv2.imread(a.image)
    if bgr is None:
        sys.exit(f"无法读取图像：{a.image}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    H, W = rgb.shape[:2]
    os.makedirs(a.case, exist_ok=True)
    ext = os.path.splitext(a.image)[1].lower() or ".png"
    existing_inputs = glob.glob(os.path.join(a.case, "00_input.*"))
    if len(existing_inputs) > 1:
        sys.exit("案例中有多张 00_input 图像，请先确认一张基准图")
    dst = existing_inputs[0] if existing_inputs else os.path.join(a.case, "00_input" + ext)
    if existing_inputs:
        if not filecmp.cmp(a.image, dst, shallow=False):
            sys.exit("案例已有不同的基准照片，请使用另一个案例文件夹")
    else:
        shutil.copyfile(a.image, dst)

    meta = caselog.load(a.case, "case_meta.json", required=False) or {}
    meta.update({"image_name": meta.get("image_name") or os.path.basename(a.image), "size_wh": [W, H],
                 "image_source": a.source or meta.get("image_source", ""),
                 "team": a.team or meta.get("team", ""), "created": meta.get("created", caselog.now())})
    caselog.save(a.case, "case_meta.json", meta)

    views.save(os.path.join(a.case, "01a_whole.png"), views.whole(rgb))
    views.save(os.path.join(a.case, "01b_tiles.png"), views.tiles(rgb))
    views.save(os.path.join(a.case, "01c_enhanced.png"), views.enhanced(rgb))
    tiles = views.tile_layout(W, H)
    outs = ["01a_whole.png", "01b_tiles.png", "01c_enhanced.png", "01_findings.json"]

    note = ""
    if not a.no_hints:
        n, frac = run_hints(rgb, a.case, a.top, a.weights)
        outs += ["01_hints.json", "01_hints.png"]
        note = f"小模型提示 {n} 处，可疑像素 {frac:.1%}"

    tpl_p = os.path.join(a.case, "01_findings.json")
    if not os.path.exists(tpl_p):
        caselog.save(a.case, "01_findings.json", {
            "image": meta["image_name"], "size_wh": [W, H], "reviewer_model": "", "manual_version": "mural-diagnose v1",
            "overall": {"content": "", "condition": "未分级", "condition_reason": "", "photo_issues": ""},
            "tiles_all": [t["id"] for t in tiles], "tiles_checked": [], "tiles_excluded": {},
            "small_model_hints_used": False,
            "findings": [], "rejected": [], "self_check": ""})

    caselog.log(a.case, "①-1 初筛准备", "OpenCV 分块/增强" + ("" if a.no_hints else " + PixelMLP 小模型提示"),
                [os.path.basename(dst)], outs, note)
    print(f"案例文件夹：{a.case}")
    print(f"图像 {W}x{H}，分 {len(tiles)} 块：" + "  ".join(f"{t['id']}={t['xywh']}" for t in tiles))
    if note:
        print(note + "（只是提示，见 01_hints.png）")
    print("下一步：按 references/02_看图步骤.md 依次读 01a_whole.png → 01b_tiles.png，填写 01_findings.json，"
          "再运行 check_findings.py")
    if not meta["image_source"]:
        print("提醒：尚未填写图片来源（--source），观察卡的来源披露栏需要它。")


if __name__ == "__main__":
    main()
