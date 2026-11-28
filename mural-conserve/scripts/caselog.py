"""Shared helpers for the mural workflow case folder (identical copy in every skill)."""
import datetime as _dt
import glob
import json
import os


def map_marks_errors(marks, box):
    """Check optional map marks after the caller validates the source-pixel box."""
    if not isinstance(marks, list):
        return ["map_marks 须为数组"]
    x, y, w, h = box
    min_points = {"point": 1, "line": 2, "polygon": 3}
    errors = []
    for i, mark in enumerate(marks, start=1):
        name = f"map_marks 第 {i} 条"
        kind = mark.get("kind") if isinstance(mark, dict) else None
        if not isinstance(kind, str) or kind not in min_points:
            errors.append(f"{name} 须指定 kind 为 point/line/polygon")
            continue
        if "tentative" in mark and type(mark["tentative"]) is not bool:
            errors.append(f"{name} 的 tentative 须为布尔值")
        points = mark.get("points")
        if not isinstance(points, list) or len(points) < min_points[kind] or (
            kind == "point" and len(points) != 1
        ):
            errors.append(f"{name} 中点须有一个坐标，线至少两个，面至少三个")
            continue
        if not all(
            isinstance(p, list) and len(p) == 2 and all(type(value) is int for value in p)
            and x <= p[0] < x + w and y <= p[1] < y + h
            for p in points
        ):
            errors.append(f"{name} 的 points 须使用定位框内的原图整数像素坐标")
    return errors


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
            raise SystemExit(f"缺少 {name}：请先完成上一步（见 README.md 的流程表）")
        return None
    return json.load(open(p, encoding="utf-8"))


def save(case, name, obj):
    with open(os.path.join(case, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def input_image(case):
    hits = sorted(glob.glob(os.path.join(case, "00_input.*")))
    if not hits:
        raise SystemExit("案例文件夹里没有 00_input.*：请先运行 mural-diagnose 的 screen.py")
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
