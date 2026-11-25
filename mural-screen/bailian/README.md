# 百炼版（通义千问 Qwen-VL）

同一本“识别手册”，换成千问来看图。输出和 Claude 版**完全同一个格式**（`01_findings.json`），所以后面的 ②–⑤ 不用改。

> 提醒：比赛**现场**只能用千问办公和百炼平台本身，不能在自己电脑上跑这些脚本。这个文件夹的用途是：
> ① 线上阶段用千问做识别；② 赛前测试“手册到底有没有让千问看得更准”；③ 把 `qwen_client.py` 里的提示词抄到百炼平台里练习（是否允许带进现场，请向主办方确认）。

## 准备

1. 在阿里云百炼控制台开通模型服务，拿到 API Key。
2. 在终端里设置（不要把 key 写进任何文件）：
   ```bash
   export DASHSCOPE_API_KEY=你的key
   ```
3. 默认模型 `qwen-vl-max`，默认地址是国内站。模型名和地址以百炼控制台为准，可以用 `--model`、`--base-url` 改（国际站：`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`）。
4. 不需要额外安装东西，只用到 Python 自带库和 opencv。

## 用法一：识别一张图

```bash
python scripts/screen.py 图片.jpg 案例文件夹 --source "图片来源"
python bailian/run_bailian.py 案例文件夹            # 加 --use-hints 会把小模型提示也告诉千问
python scripts/check_findings.py 案例文件夹         # 检查格式、出图，交给下一步
```
先想看看会发什么，不花钱：加 `--dry-run`，会生成 `01_bailian_request.json`。

## 用法二：测试手册有没有用（有手册 vs 没手册）

```bash
python bailian/eval_bailian.py MuralDH/Mural_seg 结果文件夹 --limit 40 --modes baseline,skill
```
- `baseline`：只给千问原图和输出格式，等于“不用这个 skill”。
- `skill`：给识别手册 + 整图 + 分块放大图。
- `skill_hints`：再加上小模型提示。
- 每张图每种方式调用一次。40 张 × 2 种 = 80 次调用，建议先 `--limit 10` 试试花费。
- 中途断了重跑同一条命令即可，已经问过的会直接用缓存。
- 结果在 `结果文件夹/对比结果.md`，用“10 次里中几次”的方式写。

**怎么看结果**：数据集只标了“掉了颜料、露出底子”这一类，千问如果正确报了裂缝、污渍，会被算成“没对上”。所以重点看两种方式之间谁更好，不要把数字当作真正的准确率。

先不花钱检查流程：`--mock`（用假回复跑一遍，数字没有意义）。
