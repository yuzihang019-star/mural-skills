"""Train the pixel MLP on MuralDH Mural_seg/train.

usage: python train.py <Mural_seg dir> <out weights.npz>
"""
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import compute_features  # noqa: E402
from model import PixelMLP  # noqa: E402


def load_pair(d, f):
    img = cv2.cvtColor(cv2.imread(os.path.join(d, "images", f)), cv2.COLOR_BGR2RGB)
    lab = (cv2.imread(os.path.join(d, "labels", f), cv2.IMREAD_GRAYSCALE) > 127).astype(np.float32)
    return img, lab


def sample_pixels(seg_dir, n_pos=250, n_neg=250, seed=0):
    rng = np.random.default_rng(seed)
    d = os.path.join(seg_dir, "train")
    files = sorted(os.listdir(os.path.join(d, "images")))
    Xs, ys, gid = [], [], []
    for i, f in enumerate(files):
        img, lab = load_pair(d, f)
        F = compute_features(img)
        pos = np.flatnonzero(lab.ravel() > 0.5)
        # hard negatives: half near damage (dilated ring), half anywhere
        ring = cv2.dilate(lab, np.ones((15, 15), np.uint8)) - lab
        near = np.flatnonzero(ring.ravel() > 0.5)
        neg_all = np.flatnonzero(lab.ravel() < 0.5)
        sel = []
        if len(pos):
            sel.append(rng.choice(pos, min(n_pos, len(pos)), replace=False))
        if len(near):
            sel.append(rng.choice(near, min(n_neg // 2, len(near)), replace=False))
        sel.append(rng.choice(neg_all, n_neg - (min(n_neg // 2, len(near)) if len(near) else 0), replace=False))
        idx = np.concatenate(sel)
        Xs.append(F.reshape(-1, F.shape[-1])[idx]); ys.append(lab.ravel()[idx]); gid.append(np.full(len(idx), i))
    return np.concatenate(Xs), np.concatenate(ys), np.concatenate(gid), files


def main(seg_dir, out):
    t0 = time.time()
    X, y, gid, files = sample_pixels(seg_dir)
    print(f"sampled {len(y)} px from {len(files)} imgs, pos={y.mean():.3f}, {time.time()-t0:.0f}s")
    # hold out 10% of images for threshold/epoch selection
    rng = np.random.default_rng(1)
    val_imgs = set(rng.choice(len(files), len(files) // 10, replace=False).tolist())
    vmask = np.isin(gid, list(val_imgs))
    Xtr, ytr = X[~vmask], y[~vmask]
    m = PixelMLP(X.shape[1])
    m.mu = Xtr.mean(0); m.sd = Xtr.std(0) + 1e-6
    # sampled set over-represents positives; weight back toward ~balanced loss
    w_all = np.where(ytr > 0.5, 1.0, 1.0).astype(np.float32)
    opt = {k: (np.zeros_like(v), np.zeros_like(v)) for k, v in m.p.items()}
    lr, b1, b2, step = 2e-3, 0.9, 0.999, 0
    for ep in range(12):
        perm = rng.permutation(len(ytr)); tot = 0
        for s in range(0, len(perm), 2048):
            b = perm[s:s + 2048]
            g, loss = m.grads(Xtr[b], ytr[b], w_all[b]); tot += loss * len(b); step += 1
            for k in m.p:
                mo, ve = opt[k]
                mo[:] = b1 * mo + (1 - b1) * g[k]; ve[:] = b2 * ve + (1 - b2) * g[k] ** 2
                m.p[k] -= lr * (mo / (1 - b1 ** step)) / (np.sqrt(ve / (1 - b2 ** step)) + 1e-8)
        if ep == 8:
            lr *= 0.3
        print(f"epoch {ep} loss {tot/len(ytr):.4f}  {time.time()-t0:.0f}s")

    # pick threshold maximising pixel F1 on full held-out images
    d = os.path.join(seg_dir, "train")
    best = (0, 0.5, 2.0)
    preds = []
    for i in sorted(val_imgs):
        img, lab = load_pair(d, files[i]); preds.append((img, lab))
    for sm in (0.0, 2.0, 4.0):
        m.smooth = sm
        pms = [(m.prob_map(img), lab) for img, lab in preds]
        for th in np.arange(0.3, 0.96, 0.05):
            tp = fp = fn = 0
            for pm, lab in pms:
                p = pm > th; t = lab > 0.5
                tp += np.sum(p & t); fp += np.sum(p & ~t); fn += np.sum(~p & t)
            f1 = 2 * tp / max(1, 2 * tp + fp + fn)
            if f1 > best[0]:
                best = (f1, float(th), sm)
    m.threshold, m.smooth = best[1], best[2]
    print(f"val pixel F1={best[0]:.3f} threshold={best[1]:.2f} smooth={best[2]}")
    m.save(out)
    print("saved", out, f"total {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
