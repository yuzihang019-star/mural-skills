"""Step ⑤: render the one-page A4 “AI 壁画观察卡” PDF (+ PNG preview) from 04_final.json.

usage: python render_card.py <case_dir> [--title "AI 壁画观察卡"] [--date 2026-11-25]
                             [--extra-tool "工具名：用途" ...] [--extra-source "资料名" ...]
"""
import argparse
import datetime as dt
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caselog  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

PW, PH, M = 595.0, 842.0, 30.0           # A4 in points, margin
RC = ["#e63946", "#1d78dc", "#28a03c"]   # region colours A/B/C (same as step ②)
GREY, INK, ACC = "#666666", "#1a1a1a", "#7a3e12"


def txt(p):
    if isinstance(p, dict):
        return p.get("text", "")
    return str(p)


class Page:
    def __init__(self, k):
        self.k = k
        self.fig = plt.figure(figsize=(PW / 72, PH / 72))
        self.y = M

    def text(self, x, s, fs, width, color=INK, weight="normal", gap=2.0, dy=None):
        fs = fs * self.k
        w = caselog.wrap(s, max(4, width / fs))
        n = w.count("\n") + 1
        self.fig.text(x / PW, 1 - (self.y if dy is None else dy) / PH, w, fontsize=fs, va="top",
                      color=color, weight=weight, linespacing=1.3)
        h = n * fs * 1.3 + gap * self.k
        if dy is None:
            self.y += h
        return h

    def rule(self, label):
        self.y += 3 * self.k
        self.fig.add_artist(plt.Line2D([M / PW, (PW - M) / PW], [1 - self.y / PH] * 2, color=ACC, lw=0.8))
        self.y += 3 * self.k
        self.text(M, label, 10.5, PW - 2 * M, color=ACC, weight="bold", gap=1)

    def image(self, img, x, w, h, top=None):
        top = self.y if top is None else top
        ax = self.fig.add_axes([x / PW, 1 - (top + h) / PH, w / PW, h / PH])
        ax.imshow(img); ax.set_axis_off()
        return ax


def crop(rgb, b, pad=0.45, color=(255, 230, 0)):
    H, W = rgb.shape[:2]
    x, y, w, h = b
    p = int(max(w, h) * pad) + 12
    x0, y0, x1, y1 = max(0, x - p), max(0, y - p), min(W, x + w + p), min(H, y + h + p)
    c = rgb[y0:y1, x0:x1].copy()
    cv2.rectangle(c, (x - x0, y - y0), (x - x0 + w, y - y0 + h), color, max(2, c.shape[0] // 80))
    return c


def layout(k, d, rgb, meta, log, a):
    pg = Page(k)
    fig = pg.fig
    W = PW - 2 * M
    # ---------- header
    pg.text(M, a.title, 19, W, weight="bold", gap=3)
    hdr = f"图像：{meta.get('image_name', '')}（{meta['size_wh'][0]}×{meta['size_wh'][1]}px）　"
    hdr += f"队伍：{meta.get('team') or '—'}　日期：{a.date}　流程：AI 初筛 → AI 复核 → AI 建议 → 人工复核 → 出卡"
    pg.text(M, hdr, 7.5, W, color=GREY, gap=4)
    # ---------- image row: thumbnail + regions
    H0, W0 = rgb.shape[:2]
    tw = 0.42 * W
    th = min(tw * H0 / W0, 250 * k + 40)
    tw = th * W0 / H0
    top = pg.y
    ax = pg.image(rgb, M, tw, th)
    for i, g in enumerate(d["regions"]):
        x, y, w, h = g["bbox_xywh"]
        ax.add_patch(Rectangle((x, y), w, h, fill=False, ec=RC[i % 3], lw=1.8))
        ax.text(x + 3, y + 3, g["label"], color="white", fontsize=9 * k, va="top", weight="bold",
                bbox=dict(fc=RC[i % 3], ec="none", pad=1.2))
    fig.text(M / PW, 1 - (top + th + 2) / PH, "原图缩略图（彩框为关注区域）", fontsize=6.5 * k, va="top", color=GREY)
    x0 = M + tw + 12
    cw = PW - M - x0
    cs = 62 * k
    y = top
    for i, g in enumerate(d["regions"]):
        hexc = RC[i % 3].lstrip("#")
        pg.image(crop(rgb, g["bbox_xywh"], color=tuple(int(hexc[j:j + 2], 16) for j in (0, 2, 4))), x0, cs, cs, top=y)
        tx = x0 + cs + 6
        hh = pg.text(tx, f"{g['label']}　{g['type']}（置信度：{g.get('confidence', '')}）", 8.8, cw - cs - 6,
                     color=RC[i % 3], weight="bold", dy=y)
        hh += pg.text(tx, f"现象：{g['phenomenon']}", 7.8, cw - cs - 6, dy=y + hh)
        if g.get("impact"):
            hh += pg.text(tx, f"对画面影响：{g['impact']}", 7.8, cw - cs - 6, dy=y + hh)
        if g.get("needs_onsite"):
            hh += pg.text(tx, f"仅凭图像无法确认：{g['needs_onsite']}", 7.2, cw - cs - 6, color=GREY, dy=y + hh)
        hh += pg.text(tx, f"［{g['provenance']}］", 6.5, cw - cs - 6, color=GREY, dy=y + hh)
        y += max(cs, hh) + 6 * k
    pg.y = max(top + th + 12, y) + 2
    if d.get("overall_observation"):
        pg.text(M, f"整体观察：{d['overall_observation']}　［{d.get('overall_provenance', '')}］", 8, W, gap=2)
    # ---------- suggestions
    pg.rule("保护 / 数字展示 / 公众传播建议")
    for s in d["suggestions"]:
        pg.text(M, f"【{s['category']}】{s['title']}　［{s['provenance']}］", 8.8, W, weight="bold", gap=1)
        pg.text(M + 10, f"做法：{s['content']}", 7.8, W - 10, gap=0.5)
        rel = f"（关联区域 {'、'.join(s.get('related_regions', []))}）" if s.get("related_regions") else ""
        pg.text(M + 10, f"依据{rel}：{s['basis']}", 7.8, W - 10, gap=0.5)
        pg.text(M + 10, f"可能风险：{s['risk']}", 7.8, W - 10, color="#8b1a1a", gap=3)
    # ---------- uncertainty & human review
    pg.rule("不确定性与人工复核")
    for u in d.get("uncertainty", []):
        pg.text(M, f"· {txt(u)}", 7.8, W, gap=0.5)
    for u in d.get("human_check_points", []):
        pg.text(M, f"□ 待人工核查：{txt(u)}", 7.8, W, gap=0.5)
    hr, st = d["human_review"], d["review_stats"]
    pg.text(M, f"本卡已由 {hr['reviewer']}（{hr.get('role') or '队员'}）于 {hr['reviewed_at']} 逐条复核："
               f"采纳 {st['采纳']} 项、修改 {st['修改']} 项、否决 {st['否决']} 项、人工新增 {st['人工新增']} 项"
               f"（{hr['entered_by']}；修改记录见 04_change_log.md）。签字：{hr['signature']}", 7.8, W, weight="bold", gap=2)
    # ---------- disclosure
    pg.rule("AI 参与说明与来源披露")
    m = d["ai_models"]
    pg.text(M, f"AI 生成：候选区域由离线筛查模型给出（{m['screen']}；MuralDH 测试集像素 F1≈0.18，仅作线索）；"
               f"观察说明与建议初稿由 {m['review']}{'' if m['advise'] == m['review'] else '、' + m['advise']} 生成。"
               f"人工完成：逐条复核、修改与签字确认。标注“AI 生成 · 人工采纳”的内容仍为 AI 表述。", 7.5, W, gap=1)
    src = meta.get("image_source") or "（未填写，提交前必须补充）"
    pg.text(M, f"图片来源：{src}", 7.5, W, color=INK if meta.get("image_source") else "#c00000", gap=1)
    tools = ["Python + OpenCV / NumPy / Matplotlib（开源库，图像处理与出图）",
             "筛查模型训练数据：MuralDH 敦煌壁画数据集（Dryad，doi:10.5061/dryad.bnzs7h4jd，CC0）"] + a.extra_tool
    pg.text(M, "模型与工具：" + "；".join(tools), 7.5, W, gap=1)
    refs = [r["name"] + (f"（{r['note']}）" if r.get("note") else "") for r in d.get("references", [])] + a.extra_source
    if refs:
        pg.text(M, "参考资料：" + "；".join(refs), 7.5, W, gap=1)
    # ---------- footer: traceable workflow
    steps = []
    for r in log:
        if r["step"].startswith(("①", "②", "③", "④")) and "发起" not in r["step"]:
            steps.append(f"{r['step']} {r['time'][5:16].replace('T', ' ')}")
    pg.y += 4
    pg.text(M, "过程记录：" + " → ".join(steps) + " → ⑤ 出卡", 6.5, W, color=GREY, gap=1)
    pg.text(M, "说明：本卡为基于图像的观察与辅助建议，不作为专业鉴定或文物修复施工依据；病害判断以文保专业人员现场核查为准。",
            6.5, W, color=GREY, gap=0)
    return pg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case"); ap.add_argument("--title", default="AI 壁画观察卡")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--extra-tool", action="append", default=[])
    ap.add_argument("--extra-source", action="append", default=[])
    a = ap.parse_args()
    caselog.set_cjk_font()
    d = caselog.load(a.case, "04_final.json")
    meta = caselog.load(a.case, "case_meta.json")
    log = caselog.read_log(a.case)
    rgb = cv2.cvtColor(cv2.imread(caselog.input_image(a.case)), cv2.COLOR_BGR2RGB)
    k = 1.3
    while True:
        pg = layout(k, d, rgb, meta, log, a)
        if pg.y <= PH - M - 6 or k <= 0.62:
            break
        plt.close(pg.fig); k -= 0.04
    if pg.y > PH - M + 4:
        print(f"警告：内容过多，最小字号下仍超出页面 {pg.y - PH + M:.0f}pt，请精简 04_final.json 中的文字")
    pdf = os.path.join(a.case, "05_observation_card.pdf")
    png = os.path.join(a.case, "05_observation_card.png")
    pg.fig.savefig(pdf); pg.fig.savefig(png, dpi=150); plt.close(pg.fig)
    caselog.log(a.case, "⑤ 生成观察卡", "render_card.py（Matplotlib，非 AI）", ["04_final.json"],
                ["05_observation_card.pdf", "05_observation_card.png"], f"字号缩放 {k:.2f}")
    print(f"已生成 {pdf}（A4 单页，字号缩放 {k:.2f}）")
    if not meta.get("image_source"):
        print("提醒：图片来源未填写，卡片上以红字提示。可在 case_meta.json 的 image_source 填写后重新生成。")


if __name__ == "__main__":
    main()
