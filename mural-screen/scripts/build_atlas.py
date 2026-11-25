"""Build the reference atlas (对照图册) from MuralDH Mural_seg/train.

usage: python build_atlas.py <Mural_seg dir> <out atlas dir> [--n 160] [--seed 0]

Writes 3 small sheets (each <= ~1000 px wide, 9 crops) + atlas.json:
  A_标注病害_按形态.jpg   real annotated damage, grouped: dots / patches / large loss / line-like
  B_小模型误报.jpg         small model says "damage" but annotation says none  -> what NOT to call damage
  C_小模型漏检.jpg         annotated damage the small model missed          -> what to look harder for
Yellow outline = annotation; red outline (sheet B) = small-model flagged area.
The dataset has NO damage types: group names describe shape only.
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
from model import PixelMLP  # noqa: E402

CELL = 300


def crop_tile(rgb, mask, box, label, red=None):
    H, W = rgb.shape[:2]
    x, y, w, h = box
    p = int(max(w, h) * 0.5) + 12
    x0, y0, x1, y1 = max(0, x - p), max(0, y - p), min(W, x + w + p), min(H, y + h + p)
    img = rgb[y0:y1, x0:x1].copy()
    m = (mask[y0:y1, x0:x1] > 127).astype(np.uint8)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    s = CELL / max(img.shape[:2])
    img = cv2.resize(img, (max(1, int(img.shape[1] * s)), max(1, int(img.shape[0] * s))),
                     interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
    cs = [(c * s).astype(np.int32) for c in cs]
    cv2.drawContours(img, cs, -1, (255, 255, 0), 1)
    if red is not None:
        r = (red[y0:y1, x0:x1] > 0).astype(np.uint8)
        r = cv2.resize(r, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
        rc, _ = cv2.findContours(r, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(img, rc, -1, (255, 0, 0), 1)
    tile = np.full((CELL + 22, CELL, 3), 255, np.uint8)
    tile[22:22 + img.shape[0], :img.shape[1]] = img
    cv2.putText(tile, label, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    return tile


def sheet(tiles, path, cols=3):
    if not tiles:
        return False
    blank = np.full_like(tiles[0], 255)
    rows = [np.hstack(tiles[i:i + cols] + [blank] * (cols - len(tiles[i:i + cols])))
            for i in range(0, len(tiles), cols)]
    cv2.imwrite(path, cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return True


def shape_group(area, w, h, fill):
    elong = max(w, h) / max(1, min(w, h))
    if area < 60:
        return "dots"
    if elong >= 4 or fill < 0.25:
        return "line"
    if area > 4000:
        return "large"
    return "patch"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seg"); ap.add_argument("out")
    ap.add_argument("--n", type=int, default=160); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--weights", default=os.path.join(HERE, "..", "model", "pixel_mlp.npz"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    names = sorted(os.listdir(os.path.join(a.seg, "train", "images")))
    random.Random(a.seed).shuffle(names)
    names = names[:a.n]
    model = PixelMLP.load(a.weights)

    groups = {"dots": [], "patch": [], "large": [], "line": []}
    fps, misses = [], []
    for nm in names:
        bgr = cv2.imread(os.path.join(a.seg, "train", "images", nm))
        mask = cv2.imread(os.path.join(a.seg, "train", "labels", nm), 0)
        if bgr is None or mask is None:
            continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        gt = (mask > 127).astype(np.uint8)
        pm = model.prob_map(rgb)
        if pm.shape != gt.shape:
            pm = cv2.resize(pm, (gt.shape[1], gt.shape[0]))
        pred = cv2.morphologyEx((pm > 0.6).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        # annotated components
        n, lab, st, _ = cv2.connectedComponentsWithStats(gt, 8)
        for i in range(1, n):
            x, y, w, h, ar = st[i]
            if ar < 15:
                continue
            fill = ar / float(w * h)
            groups[shape_group(ar, w, h, fill)].append((ar, nm, [int(x), int(y), int(w), int(h)]))
            hit = pred[lab == i].mean()
            if ar >= 150 and hit < 0.05:
                misses.append((ar, nm, [int(x), int(y), int(w), int(h)]))
        # predicted components with no annotation nearby = false alarm
        near = cv2.dilate(gt, np.ones((9, 9), np.uint8))
        n2, lab2, st2, _ = cv2.connectedComponentsWithStats(pred, 8)
        for i in range(1, n2):
            x, y, w, h, ar = st2[i]
            if ar >= 300 and near[lab2 == i].mean() < 0.02:
                fps.append((float(pm[lab2 == i].mean()) * ar, nm, [int(x), int(y), int(w), int(h)]))

    def pick(lst, k, rng):
        lst = sorted(lst, reverse=True)[:max(k * 4, k)]
        rng.shuffle(lst)
        out, used = [], set()
        for it in lst:
            if it[1] in used:
                continue
            used.add(it[1]); out.append(it)
            if len(out) == k:
                break
        return out

    rng = random.Random(a.seed)
    info = {"source": "MuralDH Mural_seg/train (CC0); images sampled: %d" % len(names),
            "note": "数据集只标‘有/无病害’，没有类型；分组只按形状（点状/片状/大面积/线状），不是病害类型。",
            "sheets": {}}

    def load(nm):
        rgb = cv2.cvtColor(cv2.imread(os.path.join(a.seg, "train", "images", nm)), cv2.COLOR_BGR2RGB)
        return rgb, cv2.imread(os.path.join(a.seg, "train", "labels", nm), 0)

    tiles, items = [], []
    for g, k in (("dots", 2), ("patch", 3), ("large", 2), ("line", 2)):
        for _, nm, box in pick(groups[g], k, rng):
            rgb, m = load(nm)
            tiles.append(crop_tile(rgb, m, box, f"A{len(tiles)+1} {g} {nm}"))
            items.append({"id": f"A{len(items)+1}", "group": g, "image": nm, "bbox_xywh": box})
    if sheet(tiles, os.path.join(a.out, "A_标注病害_按形态.jpg")):
        info["sheets"]["A_标注病害_按形态.jpg"] = items

    for key, src, fname in (("B", fps, "B_小模型误报.jpg"), ("C", misses, "C_小模型漏检.jpg")):
        tiles, items = [], []
        for _, nm, box in pick(src, 9, rng):
            rgb, m = load(nm)
            red = None
            if key == "B":
                red = np.zeros(m.shape, np.uint8)
                x, y, w, h = box
                red[y:y + h, x:x + w] = 1
            tiles.append(crop_tile(rgb, m, box, f"{key}{len(tiles)+1} {nm}", red))
            items.append({"id": f"{key}{len(items)+1}", "image": nm, "bbox_xywh": box})
        if sheet(tiles, os.path.join(a.out, fname)):
            info["sheets"][fname] = items

    info["counts"] = {k: len(v) for k, v in groups.items()}
    info["counts"].update({"false_alarms": len(fps), "misses": len(misses)})
    json.dump(info, open(os.path.join(a.out, "atlas.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(info["counts"], ensure_ascii=False))
    for f in sorted(os.listdir(a.out)):
        print(f, os.path.getsize(os.path.join(a.out, f)) // 1024, "KB")


if __name__ == "__main__":
    main()
