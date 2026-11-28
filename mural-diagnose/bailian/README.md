# 百炼版（通义千问 Qwen-VL）

用通义千问对基准影像做初筛，输出与本地流程共用的 `01_findings.json`。接口会发送整图和分块图，使用前确认项目允许将相应影像传给服务端。

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
python scripts/screen.py 图片.jpg 案例文件夹 --source "图片来源" --no-hints
python bailian/run_bailian.py 案例文件夹            # 仅在授权且已有提示文件时用 --use-hints
python scripts/check_findings.py 案例文件夹         # 检查格式、出图，交给下一步
```
先想看看会发什么，不花钱：加 `--dry-run`，会生成 `01_bailian_request.json`。

## 用法二：比较初筛配置

```bash
python bailian/eval_bailian.py MuralDH/Mural_seg 结果文件夹 --limit 40 --modes baseline,skill
```
- `baseline`：只给千问原图和输出格式，等于“不用这个 skill”。
- `skill`：给识别手册 + 整图 + 分块放大图。
- `skill_hints`：再加上小模型提示。
- 每张图每种方式调用一次。40 张 × 2 种 = 80 次调用，建议先 `--limit 10` 试试花费。
- 同一版本、模型、输入和模式可复用缓存。更换模型、图集或手册后请使用新的结果文件夹。
- 结果在 `结果文件夹/对比结果.md`，用“10 次里中几次”的方式写。

这组对比同时变更手册和图像视图，衡量的是整套输入配置的差异。若要单独衡量手册效果，两组需使用相同视图。数据集主要标注脱落和露底，报告中的命中率只反映候选框和这类标注的重合程度。

先不花钱检查流程：`--mock`（用假回复跑一遍，数字没有意义）。
