"""Per-pixel hand-crafted features for mural damage (crack / flaking / loss) candidates.

Only depends on numpy + opencv so it runs in offline sandboxes without torch.
"""
import cv2
import numpy as np

FEATURE_NAMES = []


def _names():
    n = ["L", "a", "b", "S", "V"]
    for s in (1, 2, 4, 8):
        n += [f"dog_{s}", f"std_{s}"]
    for k in (3, 7, 15):
        n += [f"blackhat_{k}", f"tophat_{k}"]
    n += ["grad_1", "grad_3", "lap", "dL_16", "da_16", "db_16", "edge_dens", "chroma"]
    return n


FEATURE_NAMES = _names()


def compute_features(rgb: np.ndarray) -> np.ndarray:
    """rgb: HxWx3 uint8. Returns HxWxF float32."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    gray = lab[..., 0]
    f = [lab[..., 0], lab[..., 1], lab[..., 2], hsv[..., 1], hsv[..., 2]]
    prev = gray
    for s in (1, 2, 4, 8):
        g = cv2.GaussianBlur(gray, (0, 0), s)
        f.append(prev - g)
        m2 = cv2.GaussianBlur(gray * gray, (0, 0), s)
        f.append(np.sqrt(np.maximum(m2 - g * g, 0)))
        prev = g
    g8 = gray.astype(np.uint8)
    for k in (3, 7, 15):
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        f.append(cv2.morphologyEx(g8, cv2.MORPH_BLACKHAT, ker).astype(np.float32))
        f.append(cv2.morphologyEx(g8, cv2.MORPH_TOPHAT, ker).astype(np.float32))
    for s in (1, 3):
        g = cv2.GaussianBlur(gray, (0, 0), s)
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1)
        f.append(np.sqrt(gx * gx + gy * gy))
    f.append(cv2.Laplacian(cv2.GaussianBlur(gray, (0, 0), 1), cv2.CV_32F))
    for c in range(3):
        f.append(lab[..., c] - cv2.GaussianBlur(lab[..., c], (0, 0), 16))
    edges = cv2.Canny(g8, 50, 150).astype(np.float32) / 255.0
    f.append(cv2.GaussianBlur(edges, (0, 0), 4))
    f.append(np.sqrt((lab[..., 1] - 128) ** 2 + (lab[..., 2] - 128) ** 2))
    return np.stack(f, axis=-1).astype(np.float32)
