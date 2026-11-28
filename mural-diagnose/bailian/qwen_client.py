"""Shared code for the 百炼 (DashScope, Qwen-VL) version of mural-diagnose (stage 1 screening).

- build_messages(): the shared image assessment guidance and output format.
  mode="skill"    : manual (病害百科 + 看图步骤要点 + 输出格式) + whole-with-grid view + enlarged tiles
  mode="baseline" : only the output format + the plain image (what you get without this skill)
- call_qwen(): OpenAI-compatible chat API of DashScope, stdlib only (no pip install needed).
- parse_json(): pull the JSON object out of the model reply.

API key: environment variable DASHSCOPE_API_KEY (never hard-code it, never put it in a case folder).
"""
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import views  # noqa: E402

DEFAULT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 国际站: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
DEFAULT_MODEL = "qwen-vl-max"


def _read(name):
    with open(os.path.join(SKILL, "references", name), encoding="utf-8") as f:
        return f.read()


def _b64(rgb, quality=90):
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


FORMAT_RULES = """只输出一个 JSON 对象，不要输出其他文字。格式：
{"overall":{"content":"画了什么","condition":"未分级/无法判断","assessment_status":"可评估/部分可评估/不可评估","condition_reason":"...","photo_issues":"..."},
 "tiles_checked":["T1"], "tiles_excluded":{"T2":"反光，无法判断"},
 "findings":[{"id":"F1","bbox_xywh":[x,y,w,h],"type":"疑似xxx","category":"脱落类/裂缝类/结构盐分类/污染类/颜色变化类/人为损害/其他",
   "photo_grade":"A/B/C","evidence":"看得到的颜色形状边缘","layer_exposed":"...","confidence":"高/中/低",
   "alternatives":"替代解释及区分依据","how_to_verify":"B/C级必填","source":"大模型看图"}],
 "rejected":[{"bbox_xywh":[x,y,w,h],"looked_like":"...","why_not":"..."}],
 "small_model_hints_used":false, "self_check":"..."}
坐标一律是原图像素（左上角 x,y 和宽高 w,h）。没有可定位现象时 findings 为空数组。用 condition_reason 区分在已评范围内未见明显异常与影像不足以判断。只记录实际检查过的分块。根据提供的小模型提示实际回看时将 small_model_hints_used 标为 true。"""

def system_prompt(mode):
    role = "你负责彩绘表面的影像状态初筛。记录可见现象、初步解释和图像限制。"
    if mode == "baseline":
        return role + "\n" + FORMAT_RULES
    instructions = _read("02_看图步骤.md")
    manual = _read("01_病害百科.md")
    return role + "\n\n" + instructions + "\n\n" + manual + "\n\n" + FORMAT_RULES


def build_messages(rgb, mode="skill", hints=None):
    H, W = rgb.shape[:2]
    tiles = views.tile_layout(W, H)
    if mode == "baseline":
        content = [{"type": "image_url", "image_url": {"url": _b64(rgb)}},
                   {"type": "text", "text": f"图像尺寸 {W}x{H}。请按格式记录可见现象和照片限制。"}]
    else:
        txt = (f"图像尺寸 {W}x{H}，分块：" + "，".join(f"{t['id']}={t['xywh']}" for t in tiles) +
               "。第 1 张是整图（边上有原图坐标刻度），第 2 张是分块放大图。按手册记录实际检查和因影像限制无法检查的分块，然后输出 JSON。")
        if hints:
            txt += ("\n离线小模型提示了下列可能有脱落的位置（它只对脱落和露底提供线索，回到原图确认）："
                    + json.dumps([h["bbox_xywh"] for h in hints]))
        content = [{"type": "image_url", "image_url": {"url": _b64(views.whole(rgb))}},
                   {"type": "image_url", "image_url": {"url": _b64(views.tiles(rgb))}},
                   {"type": "text", "text": txt}]
    return [{"role": "system", "content": system_prompt(mode)}, {"role": "user", "content": content}], \
        [t["id"] for t in tiles]


def call_qwen(messages, model=DEFAULT_MODEL, base=DEFAULT_BASE, timeout=180, retries=3):
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        sys.exit("没有找到 DASHSCOPE_API_KEY 环境变量。请先 export DASHSCOPE_API_KEY=你的百炼 key")
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.1}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body, method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode())
            return d["choices"][0]["message"]["content"], d.get("usage", {})
        except (urllib.error.URLError, TimeoutError, KeyError) as e:
            msg = e.read().decode()[:300] if hasattr(e, "read") else str(e)
            if i == retries - 1:
                raise RuntimeError(f"百炼调用失败：{msg}")
            time.sleep(3 * (i + 1))


def parse_json(text):
    t = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        return json.loads(t[a:b + 1])
    except json.JSONDecodeError:
        return None
