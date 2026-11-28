"""Make small images for visual review (keeps context small: one downscaled file per call).

usage:
  python view.py <case_dir> whole [--max 1000]            -> <case>/_view_whole.png
  python view.py <case_dir> box x,y,w,h [x,y,w,h ...]     -> <case>/_view_boxes.png (context crops, tiled)
Coordinates are original-image pixels.
"""
import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caselog  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case"); ap.add_argument("mode", choices=["whole", "box"])
    ap.add_argument("boxes", nargs="*"); ap.add_argument("--max", type=int, default=1000)
    ap.add_argument("--cell", type=int, default=360)
    a = ap.parse_args()
    rgb = cv2.cvtColor(cv2.imread(caselog.input_image(a.case)), cv2.COLOR_BGR2RGB)
    H, W = rgb.shape[:2]
    if a.mode == "whole":
        s = min(1.0, a.max / max(H, W))
        out = cv2.resize(rgb, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
        step = max(1, int(round(max(H, W) / 8 / 50.0)) * 50)  # coordinate grid every ~1/8 side
        for v in range(step, max(H, W), step):
            if v < W:
                cv2.line(out, (int(v * s), 0), (int(v * s), out.shape[0]), (255, 255, 255), 1)
                cv2.putText(out, str(v), (int(v * s) + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
            if v < H:
                cv2.line(out, (0, int(v * s)), (out.shape[1], int(v * s)), (255, 255, 255), 1)
                cv2.putText(out, str(v), (2, int(v * s) - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        p = os.path.join(a.case, "_view_whole.png")
    else:
        tiles = []
        for b in a.boxes:
            x, y, w, h = [int(float(t)) for t in b.split(",")]
            pad = int(max(w, h) * 0.5) + 16
            x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
            crop = rgb[y0:y1, x0:x1].copy()
            cv2.rectangle(crop, (x - x0, y - y0), (x - x0 + w, y - y0 + h), (255, 255, 0), max(1, crop.shape[0] // 150))
            s = a.cell / max(crop.shape[:2])
            crop = cv2.resize(crop, (max(1, int(crop.shape[1] * s)), max(1, int(crop.shape[0] * s))))
            t = np.full((a.cell + 24, a.cell, 3), 255, np.uint8)
            t[24:24 + crop.shape[0], :crop.shape[1]] = crop
            cv2.putText(t, b, (4, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            tiles.append(t)
        out = np.hstack(tiles) if tiles else np.full((50, 200, 3), 255, np.uint8)
        p = os.path.join(a.case, "_view_boxes.png")
    cv2.imwrite(p, out[..., ::-1])
    print(p)


if __name__ == "__main__":
    main()
