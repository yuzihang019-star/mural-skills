"""Find damage *candidate* regions on a mural image and emit JSON + overlay.

usage: python detect.py <image> [--top 5] [--out out_prefix] [--weights path]

Outputs <out>_candidates.json and <out>_overlay.png. Boxes are in ORIGINAL image pixels.
The model is a weak screener (pixel F1 ~0.18 on MuralDH test). Treat every box as
"look here", never as a diagnosis; the damage type hint is a shape/colour heuristic.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from model import PixelMLP  # noqa: E402

DEFAULT_W = os.path.join(HERE, "..", "model", "pixel_mlp.npz")


def type_hint(rgb, mask_c, box):
    """Heuristic label from shape + brightness vs surroundings."""
    x, y, w, h = box
    comp = mask_c[y:y + h, x:x + w]
    area = int(comp.sum())
    fill = area / max(1, w * h)
    elong = max(w, h) / max(1, min(w, h))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    ring = cv2.dilate(mask_c.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & ~mask_c
    inside = gray[mask_c].mean() if mask_c.any() else 0
    around = gray[ring].mean() if ring.any() else inside
    dl = float(inside - around)
    if fill < 0.25 or elong > 4:
        return "疑似裂隙 crack-like", dl
    if dl > 12:
        return "疑似起甲/脱落露底 flaking/loss (lighter)", dl
    if dl < -12:
        return "疑似污染/烟熏/霉斑 stain (darker)", dl
    return "疑似颜料层褪变 pigment change", dl


def candidates(model, rgb, top=5, min_area_frac=2e-4):
    pm, scale = model.predict_large(rgb)
    small = cv2.resize(rgb, (pm.shape[1], pm.shape[0]), interpolation=cv2.INTER_AREA) if scale < 1 else rgb
    mask = (pm > model.threshold).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    min_area = max(20, int(min_area_frac * mask.size))
    out = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < min_area:
            continue
        comp = lab == i
        conf = float(pm[comp].mean())
        score = conf * np.sqrt(a)
        hint, dl = type_hint(small, comp, (x, y, w, h))
        out.append({"score": round(float(score), 3), "mean_prob": round(conf, 3),
                    "area_frac": round(float(a) / mask.size, 5),
                    "bbox_xywh": [int(round(v / scale)) for v in (x, y, w, h)],
                    "type_hint": hint, "brightness_vs_surround": round(dl, 1)})
    out.sort(key=lambda d: -d["score"])
    # suppress boxes mostly covered by a higher-scoring kept box
    kept = []
    for d in out:
        x, y, w, h = d["bbox_xywh"]
        dup = False
        for k in kept:
            X, Y, Wk, Hk = k["bbox_xywh"]
            iw = max(0, min(x + w, X + Wk) - max(x, X)); ih = max(0, min(y + h, Y + Hk) - max(y, Y))
            if iw * ih > 0.5 * min(w * h, Wk * Hk):
                dup = True; break
        if not dup:
            kept.append(d)
    out = kept
    for k, d in enumerate(out):
        d["id"] = k + 1
    return out[:top], pm, scale, float(mask.mean())


def overlay(rgb, pm, scale, cands, path, max_side=1400):
    H, W = rgb.shape[:2]
    s = min(1.0, max_side / max(H, W))
    vis = cv2.resize(rgb, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    heat = cv2.resize(pm, (vis.shape[1], vis.shape[0]))
    hm = cv2.applyColorMap((np.clip(heat, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_JET)[..., ::-1]
    alpha = (np.clip((heat - 0.3) / 0.7, 0, 1) * 0.5)[..., None]
    vis = (vis * (1 - alpha) + hm * alpha).astype(np.uint8)
    for c in cands:
        x, y, w, h = [int(v * s) for v in c["bbox_xywh"]]
        cv2.rectangle(vis, (x, y), (x + w, y + h), (255, 255, 0), 2)
        cv2.putText(vis, str(c["id"]), (x + 3, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
    cv2.imwrite(path, vis[..., ::-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image"); ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--out", default=None); ap.add_argument("--weights", default=DEFAULT_W)
    a = ap.parse_args()
    m = PixelMLP.load(a.weights)
    bgr = cv2.imread(a.image)
    if bgr is None:
        sys.exit(f"cannot read {a.image}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    cands, pm, scale, frac = candidates(m, rgb, a.top)
    out = a.out or os.path.splitext(a.image)[0]
    res = {"image": os.path.basename(a.image), "size_wh": [rgb.shape[1], rgb.shape[0]],
           "flagged_area_frac": round(frac, 4), "threshold": m.threshold,
           "model_note": "weak screener: pixel F1~0.18 on MuralDH test; boxes are leads for human/VLM review",
           "candidates": cands}
    with open(out + "_candidates.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    overlay(rgb, pm, scale, cands, out + "_overlay.png")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
