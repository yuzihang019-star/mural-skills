"""Shared code for the 百炼 (DashScope, Qwen-VL) version of mural-screen.

- build_messages(): the SAME identification manual the Claude version uses, turned into a prompt.
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
{"overall":{"content":"画了什么","condition":"好/一般/差","condition_reason":"...","photo_issues":"..."},
 "tiles_checked":["T1",...],
 "findings":[{"id":"F1","bbox_xywh":[x,y,w,h],"type":"疑似xxx","category":"脱落类/裂缝类/结构盐分类/污染类/颜色变化类/人为损害/其他",
   "photo_grade":"A/B/C","evidence":"看得到的颜色形状边缘","layer_exposed":"...","confidence":"高/中/低",
   "alternatives":"排除了什么误判","how_to_verify":"B/C级必填","source":"大模型看图"}],
 "rejected":[{"bbox_xywh":[x,y,w,h],"looked_like":"...","why_not":"..."}],
 "self_check":"..."}
坐标一律是原图像素（左上角 x,y 和宽高 w,h）。没有病害时 findings 为空数组，不要编造。"""

STEPS = """看图规则（必须遵守）：
1. 先看第 1 张图（整图+坐标刻度+分块编号）：画了什么、整体保存状况、拍摄问题。
2. 再看第 2 张图（每个分块单独放大，标了块号和原图坐标范围）：每一块都要过一遍检查表，小病害只有在这里看得到。
3. 检查表：颜色突变+边缘不规则+切断线条→颜料层脱落；露出土色颗粒→地仗脱落；散布浅色小点→点状脱落（先排除装饰和噪点）；
   鳞片状带亮边→疑似起甲；不理会画面内容的锯齿深线→裂隙（先排除墨线）；网状小格→龟裂；白色粉状→疑似盐霜/酥碱；
   黑褐渐变或流淌痕→烟熏/水渍；成簇黑绿斑→疑似霉斑；笔直划线或后人字迹→划痕/涂写；同色深浅不一→可能褪色。
4. 最常见的误判：把原画墨线当裂隙；把原画浅色（白脸、白衣、珠串、团花）当脱落；把规则排列的点饰当点状脱落。拿不准就放进 rejected 并写理由。
5. B 级病害 confidence 最高“中”，C 级只能“低”，B/C 级必须写 how_to_verify。证据只写图里看得到的东西，不写年代、材料成分。
6. 框住病害本身，不要把半幅画框进去。宁可少报，不要编造。"""


def system_prompt(mode):
    if mode == "baseline":
        return "你是壁画保护助手。找出图中壁画的病害。\n" + FORMAT_RULES
    manual = _read("01_病害百科.md")
    return ("你是壁画病害识别员，严格按下面的识别手册看图。\n\n" + STEPS + "\n\n【病害百科】\n" + manual +
            "\n\n【输出格式】\n" + FORMAT_RULES)


def build_messages(rgb, mode="skill", hints=None):
    H, W = rgb.shape[:2]
    tiles = views.tile_layout(W, H)
    if mode == "baseline":
        content = [{"type": "image_url", "image_url": {"url": _b64(rgb)}},
                   {"type": "text", "text": f"图像尺寸 {W}x{H}。请找出病害并按格式输出 JSON。"}]
    else:
        txt = (f"图像尺寸 {W}x{H}，分块：" + "，".join(f"{t['id']}={t['xywh']}" for t in tiles) +
               "。第 1 张是整图（边上有原图坐标刻度），第 2 张是分块放大图。按手册步骤看完全部分块后输出 JSON。")
        if hints:
            txt += ("\n离线小模型提示了下列可能有脱落的位置（约四分之三是误报，只能提醒你回去再看，不能当结论）："
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
