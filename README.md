# 壁画智护 Skills

用于壁画（尤其敦煌石窟壁画）病害识别与“AI 壁画观察卡”生成的 Claude Skills。

## 观察卡工作流（按顺序使用）

| 步骤 | Skill | 作用 |
|---|---|---|
| ① | `mural-screen` | 病害识别，输出 `01_candidates.json` |
| ② | `mural-review` | AI 视觉复核，输出 `02_review.json` |
| ③ | `mural-advise` | 建议、依据与风险，输出 `03_advice.json` |
| ④ | `mural-human-check` | 人工复核，输出 `04_final.json` |
| ⑤ | `mural-card` | 生成一页 A4 观察卡 PDF |

详见 [WORKFLOW.md](WORKFLOW.md)；`make_report_pdf.py` 为报告 PDF 生成脚本。

## 安装

把对应文件夹打包为 zip 并改扩展名为 `.skill`，在 Claude 中上传即可。

## 注意

`mural-screen/bailian` 调用阿里云百炼，请通过环境变量 `DASHSCOPE_API_KEY` 提供密钥，切勿写入代码或案例文件夹。
