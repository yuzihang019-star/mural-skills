"""Image views that help a vision model look carefully: whole+grid, tiles, contrast-enhanced, zoom, boxes.

All coordinates are ORIGINAL image pixels. Labels are ASCII so no CJK font is needed.
"""
import cv2
import numpy as np

COLORS = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180),
          (70, 240, 240), (240, 50, 230), (128, 128, 0), (0, 0, 128), (170, 110, 40)]


def tile_layout(w, h):
    n = 2 if max(w, h) <= 700 else 3
    xs = np.linspace(0, w, n + 1).astype(int)
    ys = np.linspace(0, h, n + 1).astype(int)
    tiles = []
    k = 1
    for r in range(n):
        for c in range(n):
            tiles.append({"id": f"T{k}", "xywh": [int(xs[c]), int(ys[r]), int(xs[c + 1] - xs[c]), int(ys[r + 1] - ys[r])]})
            k += 1
    return tiles


def _txt(img, s, org, scale=0.5, color=(0, 0, 0), bg=(255, 255, 255)):
    (tw, th), b = cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    x, y = org
    cv2.rectangle(img, (x - 1, y - th - 2), (x + tw + 1, y + b), bg, -1)
    cv2.putText(img, s, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def whole(rgb, max_side=900):
    """Downscaled image with a labelled coordinate grid and tile boundaries."""
    H, W = rgb.shape[:2]
    s = min(1.0, max_side / max(H, W))
    img = cv2.resize(rgb, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA) if s < 1 else rgb.copy()
    # ticks only on the border: full grid lines hide thin cracks/scratches, which are often white too
    step = max(50, int(round(max(W, H) / 6 / 50.0)) * 50)
    ih, iw = img.shape[:2]
    for x in range(step, W, step):
        X = int(x * s)
        cv2.line(img, (X, 0), (X, 8), (255, 255, 0), 2)
        cv2.line(img, (X, ih - 8), (X, ih), (255, 255, 0), 2)
        _txt(img, str(x), (X + 2, 20), 0.38)
    for y in range(step, H, step):
        Y = int(y * s)
        cv2.line(img, (0, Y), (8, Y), (255, 255, 0), 2)
        cv2.line(img, (iw - 8, Y), (iw, Y), (255, 255, 0), 2)
        _txt(img, str(y), (10, Y + 4), 0.38)
    for t in tile_layout(W, H):
        x, y, w, h = t["xywh"]
        cv2.rectangle(img, (int(x * s), int(y * s)), (int((x + w) * s) - 1, int((y + h) * s) - 1), (255, 0, 0), 2)
        _txt(img, t["id"], (int(x * s) + 4, int((y + h) * s) - 6), 0.6, (255, 0, 0))
    return img


def tiles(rgb, cell=420):
    """Each tile upscaled to `cell` px, laid out in the same grid, labelled with id + coordinates."""
    H, W = rgb.shape[:2]
    lay = tile_layout(W, H)
    n = int(round(len(lay) ** 0.5))
    out = []
    for t in lay:
        x, y, w, h = t["xywh"]
        crop = rgb[y:y + h, x:x + w]
        s = cell / max(w, h)
        crop = cv2.resize(crop, (int(w * s), int(h * s)), interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
        canvas = np.full((cell + 24, cell, 3), 255, np.uint8)
        canvas[24:24 + crop.shape[0], :crop.shape[1]] = crop
        _txt(canvas, f"{t['id']}  x{x}-{x + w} y{y}-{y + h}", (4, 17), 0.5)
        out.append(canvas)
    rows = [np.hstack(out[i:i + n]) for i in range(0, len(out), n)]
    pad = 6
    rows = [np.pad(r, ((pad, pad), (0, 0), (0, 0)), constant_values=200) for r in rows]
    return np.vstack(rows)


def enhanced(rgb, max_side=900):
    """CLAHE on lightness: makes loss edges, fine cracks and pale deposits easier to SEE (not to judge colour)."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(l)
    img = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2RGB)
    H, W = img.shape[:2]
    s = min(1.0, max_side / max(H, W))
    if s < 1:
        img = cv2.resize(img, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    _txt(img, "CONTRAST-ENHANCED (colours altered)", (4, 16), 0.5, (200, 0, 0))
    return img


def zoom(rgb, boxes, labels=None, cell=320, pad_frac=0.6, cols=3):
    """Context crop per box (box outlined), tiled into one image."""
    H, W = rgb.shape[:2]
    out = []
    for i, (x, y, w, h) in enumerate(boxes):
        p = int(max(w, h) * pad_frac) + 16
        x0, y0, x1, y1 = max(0, x - p), max(0, y - p), min(W, x + w + p), min(H, y + h + p)
        crop = rgb[y0:y1, x0:x1].copy()
        cv2.rectangle(crop, (x - x0, y - y0), (x - x0 + w, y - y0 + h), (255, 255, 0), max(1, crop.shape[0] // 150))
        s = cell / max(crop.shape[:2])
        crop = cv2.resize(crop, (max(1, int(crop.shape[1] * s)), max(1, int(crop.shape[0] * s))),
                          interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
        tile = np.full((cell + 26, cell, 3), 255, np.uint8)
        tile[26:26 + crop.shape[0], :crop.shape[1]] = crop
        lab = labels[i] if labels else f"#{i + 1}"
        _txt(tile, f"{lab}  [{x},{y},{w},{h}]", (4, 18), 0.5)
        out.append(tile)
    if not out:
        t = np.full((120, cell, 3), 255, np.uint8)
        _txt(t, "no boxes", (10, 60), 0.7)
        return t
    cols = min(cols, len(out))
    blank = np.full_like(out[0], 255)
    rows = [np.hstack(out[i:i + cols] + [blank] * (cols - len(out[i:i + cols]))) for i in range(0, len(out), cols)]
    return np.vstack(rows)


def draw_boxes(rgb, boxes, labels, max_side=1000):
    H, W = rgb.shape[:2]
    s = min(1.0, max_side / max(H, W))
    img = cv2.resize(rgb, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA) if s < 1 else rgb.copy()
    lw = max(2, img.shape[0] // 250)
    for i, ((x, y, w, h), lab) in enumerate(zip(boxes, labels)):
        c = COLORS[i % len(COLORS)]
        p0, p1 = (int(x * s), int(y * s)), (int((x + w) * s), int((y + h) * s))
        cv2.rectangle(img, p0, p1, c, lw)
        _txt(img, lab, (p0[0] + 2, max(14, p0[1] - 3)), 0.55, c)
    return img


def save(path, rgb):
    cv2.imwrite(path, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
