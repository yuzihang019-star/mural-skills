"""Make one view image for the vision model to read.

usage:
  python look.py <case> whole                 -> 01a_whole.png
  python look.py <case> tiles                 -> 01b_tiles.png
  python look.py <case> enhanced              -> 01c_enhanced.png
  python look.py <case> zoom x,y,w,h [...]    -> 01d_zoom.png  (all boxes in ONE image; original pixels)
  python look.py <case> zoom-enh x,y,w,h ...  -> 01d_zoom.png  but contrast-enhanced
"""
import glob
import os
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import views  # noqa: E402


def load_input(case):
    f = sorted(glob.glob(os.path.join(case, "00_input.*")))
    if not f:
        sys.exit("案例里没有 00_input.*，请先运行 screen.py")
    return cv2.cvtColor(cv2.imread(f[0]), cv2.COLOR_BGR2RGB)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    case, mode, boxes = sys.argv[1], sys.argv[2], sys.argv[3:]
    rgb = load_input(case)
    if mode == "whole":
        out, img = "01a_whole.png", views.whole(rgb)
    elif mode == "tiles":
        out, img = "01b_tiles.png", views.tiles(rgb)
    elif mode == "enhanced":
        out, img = "01c_enhanced.png", views.enhanced(rgb)
    elif mode in ("zoom", "zoom-enh"):
        bx = [tuple(int(v) for v in b.split(",")) for b in boxes]
        if not bx or any(len(b) != 4 for b in bx):
            sys.exit("zoom 需要至少一个 x,y,w,h")
        src = rgb
        if mode == "zoom-enh":
            lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
            lab[..., 0] = cv2.createCLAHE(3.0, (8, 8)).apply(lab[..., 0])
            src = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        out, img = "01d_zoom.png", views.zoom(src, bx)
    else:
        sys.exit(__doc__)
    p = os.path.join(case, out)
    views.save(p, img)
    print(p)


if __name__ == "__main__":
    main()
