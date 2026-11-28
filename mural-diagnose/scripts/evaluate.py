"""Evaluate on Mural_seg/test: pixel P/R/F1/IoU + top-K box hit rate vs random boxes.

usage: python evaluate.py <Mural_seg dir> [weights] [out.json]
A box "hits" when >=10% of its pixels are labelled damage.
Random baseline: the same box sizes placed uniformly at random (20 draws per image).
"""
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from detect import DEFAULT_W, candidates  # noqa: E402
from model import PixelMLP  # noqa: E402


def main(seg, wpath=DEFAULT_W, out=None):
    m = PixelMLP.load(wpath)
    d = os.path.join(seg, "test")
    files = sorted(os.listdir(os.path.join(d, "images")))
    rng = np.random.default_rng(0)
    tp = fp = fn = 0
    iou_list = []
    hits = rand_hits = nbox = 0
    dens = rdens = 0.0
    any_hit = 0
    for f in files:
        rgb = cv2.cvtColor(cv2.imread(os.path.join(d, "images", f)), cv2.COLOR_BGR2RGB)
        t = cv2.imread(os.path.join(d, "labels", f), cv2.IMREAD_GRAYSCALE) > 127
        cands, pm, _, _ = candidates(m, rgb, top=3)
        p = pm > m.threshold
        a, b, c = np.sum(p & t), np.sum(p & ~t), np.sum(~p & t)
        tp += a; fp += b; fn += c
        if t.any():
            iou_list.append(a / max(1, a + b + c))
        H, W = t.shape
        img_hit = False
        for cd in cands:
            x, y, w, h = cd["bbox_xywh"]
            dd = t[y:y + h, x:x + w].mean()
            dens += dd; hits += dd >= 0.10; nbox += 1; img_hit |= dd >= 0.10
            for _ in range(20):
                rx, ry = rng.integers(0, W - w + 1), rng.integers(0, H - h + 1)
                rd = t[ry:ry + h, rx:rx + w].mean()
                rdens += rd / 20; rand_hits += (rd >= 0.10) / 20
        any_hit += img_hit
    prec, rec = tp / max(1, tp + fp), tp / max(1, tp + fn)
    res = {
        "n_test_images": len(files), "threshold": m.threshold,
        "pixel_precision": round(float(prec), 3), "pixel_recall": round(float(rec), 3),
        "pixel_f1": round(float(2 * prec * rec / max(1e-9, prec + rec)), 3),
        "global_iou": round(float(tp / max(1, tp + fp + fn)), 3),
        "mean_image_iou": round(float(np.mean(iou_list)), 3),
        "label_positive_frac": round(float((tp + fn) / (len(files) * 512 * 512)), 4),
        "top3_boxes": nbox,
        "top3_box_hit_rate": round(hits / max(1, nbox), 3),
        "random_box_hit_rate": round(rand_hits / max(1, nbox), 3),
        "top3_mean_damage_density": round(dens / max(1, nbox), 3),
        "random_mean_damage_density": round(rdens / max(1, nbox), 3),
        "images_with_>=1_hit_in_top3": round(any_hit / len(files), 3),
    }
    res["hit_rate_lift"] = round(res["top3_box_hit_rate"] / max(1e-9, res["random_box_hit_rate"]), 2)
    print(json.dumps(res, indent=2))
    if out:
        json.dump(res, open(out, "w"), indent=2)


if __name__ == "__main__":
    main(sys.argv[1], *(sys.argv[2:4]))
