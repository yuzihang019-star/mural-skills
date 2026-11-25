"""Shared helpers for the mural workflow case folder (identical copy in every skill)."""
import datetime as _dt
import glob
import json
import os


def now():
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def log(case, step, tool, inputs, outputs, note=""):
    rec = {"time": now(), "step": step, "tool": tool, "inputs": inputs, "outputs": outputs}
    if note:
        rec["note"] = note
    with open(os.path.join(case, "workflow_log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_log(case):
    p = os.path.join(case, "workflow_log.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def load(case, name, required=True):
    p = os.path.join(case, name)
    if not os.path.exists(p):
        if required:
            raise SystemExit(f"缺少 {name}：请先完成上一步（见 WORKFLOW.md）")
        return None
    return json.load(open(p, encoding="utf-8"))


def save(case, name, obj):
    with open(os.path.join(case, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def input_image(case):
    hits = sorted(glob.glob(os.path.join(case, "00_input.*")))
    if not hits:
        raise SystemExit("案例文件夹里没有 00_input.*：请先运行 mural-screen")
    return hits[0]


def set_cjk_font():
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    pats = ["/usr/share/fonts/**/NotoSansCJK*.ttc", "/usr/share/fonts/**/NotoSerifCJK*.ttc",
            "/usr/share/fonts/**/*wqy*.tt*", "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti*.ttc", "/Library/Fonts/Arial Unicode.ttf",
            "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]
    for p in pats:
        for f in sorted(glob.glob(p, recursive=True)):
            if "Bold" in f and "Regular" not in f:
                continue
            font_manager.fontManager.addfont(f)
            name = font_manager.FontProperties(fname=f).get_name()
            plt.rcParams["font.family"] = [name]
            return name
    return None


def wrap(s, n):
    """Wrap by display width: CJK chars count 1, ASCII 0.55."""
    if not s:
        return ""
    out = []
    for para in str(s).split("\n"):
        cur, w = "", 0.0
        for ch in para:
            cw = 0.55 if ord(ch) < 0x2E80 else 1.0
            if w + cw > n and cur:
                out.append(cur); cur, w = "", 0.0
                if ch == " ":
                    continue
            cur += ch; w += cw
        out.append(cur)
    return "\n".join(out)
