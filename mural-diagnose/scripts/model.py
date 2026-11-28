"""Tiny NumPy MLP (F -> 48 -> 24 -> 1) for per-pixel damage probability."""
import cv2
import numpy as np

from features import compute_features


def _relu(x):
    return np.maximum(x, 0)


class PixelMLP:
    def __init__(self, n_in, h1=48, h2=24, seed=0):
        r = np.random.default_rng(seed)
        self.p = {
            "W1": r.normal(0, np.sqrt(2 / n_in), (n_in, h1)).astype(np.float32),
            "b1": np.zeros(h1, np.float32),
            "W2": r.normal(0, np.sqrt(2 / h1), (h1, h2)).astype(np.float32),
            "b2": np.zeros(h2, np.float32),
            "W3": r.normal(0, np.sqrt(1 / h2), (h2, 1)).astype(np.float32),
            "b3": np.zeros(1, np.float32),
        }
        self.mu = np.zeros(n_in, np.float32)
        self.sd = np.ones(n_in, np.float32)
        self.threshold = 0.5
        self.smooth = 2.0

    # ---- forward / backward -------------------------------------------------
    def logits(self, X, cache=False):
        p = self.p
        Xn = (X - self.mu) / self.sd
        z1 = Xn @ p["W1"] + p["b1"]; a1 = _relu(z1)
        z2 = a1 @ p["W2"] + p["b2"]; a2 = _relu(z2)
        z3 = (a2 @ p["W3"] + p["b3"])[:, 0]
        if cache:
            return z3, (Xn, z1, a1, z2, a2)
        return z3

    def grads(self, X, y, w):
        z, (Xn, z1, a1, z2, a2) = self.logits(X, cache=True)
        pr = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        dz = ((pr - y) * w / w.sum())[:, None].astype(np.float32)
        p = self.p
        g = {"W3": a2.T @ dz, "b3": dz.sum(0)}
        d2 = (dz @ p["W3"].T) * (z2 > 0)
        g["W2"] = a1.T @ d2; g["b2"] = d2.sum(0)
        d1 = (d2 @ p["W2"].T) * (z1 > 0)
        g["W1"] = Xn.T @ d1; g["b1"] = d1.sum(0)
        eps = 1e-7
        loss = -np.sum(w * (y * np.log(pr + eps) + (1 - y) * np.log(1 - pr + eps))) / w.sum()
        return g, loss

    # ---- image-level inference ----------------------------------------------
    def prob_map(self, rgb):
        F = compute_features(rgb)
        h, w, c = F.shape
        z = self.logits(F.reshape(-1, c)).reshape(h, w)
        pr = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        if self.smooth > 0:
            pr = cv2.GaussianBlur(pr.astype(np.float32), (0, 0), self.smooth)
        return pr

    def predict_large(self, rgb, tile=512, max_side=2048):
        """Runs on any size image: downsizes so the long side <= max_side, tiles at 512."""
        H, W = rgb.shape[:2]
        scale = min(1.0, max_side / max(H, W))
        img = cv2.resize(rgb, (int(W * scale), int(H * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else rgb
        h, w = img.shape[:2]
        out = np.zeros((h, w), np.float32)
        pad = 32
        for y0 in range(0, h, tile):
            for x0 in range(0, w, tile):
                ya, xa = max(0, y0 - pad), max(0, x0 - pad)
                yb, xb = min(h, y0 + tile + pad), min(w, x0 + tile + pad)
                pm = self.prob_map(img[ya:yb, xa:xb])
                out[y0:min(h, y0 + tile), x0:min(w, x0 + tile)] = pm[y0 - ya:y0 - ya + min(tile, h - y0), x0 - xa:x0 - xa + min(tile, w - x0)]
        return out, scale

    # ---- io ------------------------------------------------------------------
    def save(self, path):
        np.savez(path, mu=self.mu, sd=self.sd, threshold=self.threshold, smooth=self.smooth, **self.p)

    @classmethod
    def load(cls, path):
        d = np.load(path)
        m = cls(d["W1"].shape[0], d["W1"].shape[1], d["W2"].shape[1])
        for k in m.p:
            m.p[k] = d[k]
        m.mu, m.sd = d["mu"], d["sd"]
        m.threshold, m.smooth = float(d["threshold"]), float(d["smooth"])
        return m
