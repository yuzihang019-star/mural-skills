# 壁画智护 Skills

用于壁画（尤其敦煌石窟壁画）病害识别、保护建议和人工复核的 Claude Skills。

## 三步工作流（2026-11-27）

三个技能按顺序使用，读取和写入同一个案例文件夹。

| 步骤 | Skill | 主要产出 |
|---|---|---|
| ① 病害识别分析 | [`mural-diagnose`](mural-diagnose/SKILL.md) | 按区域记录可见现象、病害判断与人工核查方法，生成 `02_review.json` |
| ② 保护建议 | [`mural-conserve`](mural-conserve/SKILL.md) | 生成保护建议 `03_conservation.json` 和独立报告 `03_report.pdf` |
| ③ 人工复核 | [`mural-review-pdf`](mural-review-pdf/SKILL.md) | 生成逐条复核单 `04_review_form.pdf`，录入决定后生成定稿和修改记录 |

## 安装

把对应文件夹打包为 zip 并改扩展名为 `.skill`，在 Claude 中上传即可。

## 注意

`mural-diagnose/bailian` 调用阿里云百炼，请通过环境变量 `DASHSCOPE_API_KEY` 提供密钥，切勿写入代码或案例文件夹。
