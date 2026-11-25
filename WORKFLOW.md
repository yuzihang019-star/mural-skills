# 壁画观察卡工作流（5 个 skill）

本文件说明 5 个 skill 怎么串起来。它们是同一条流程上的 5 个环节，每个环节只做一件事，结果写进同一个“案例文件夹”，下一个环节读上一个环节的产物。录演示视频时按编号依次打开这些文件，就能展示“输入 → AI 处理 → 人工复核 → 输出”的全过程。

```
原图
 │  ① mural-screen       按识别手册看图识别病害 → 01_findings.json / 01_candidates.json / 01_crops.png
 │  ② mural-review       AI 视觉复核，选 1–3 处 → 02_review.json / 02_regions.png
 │  ③ mural-advise       建议 + 依据 + 风险     → 03_advice.json
 │  ④ mural-human-check  队员人工复核并签字     → 04_review_form.md / 04_review_sheet.png / 04_final.json / 04_change_log.md
 ▼  ⑤ mural-card         生成一页观察卡         → 05_observation_card.pdf / 05_observation_card.png
```

## 案例文件夹约定

| 文件 | 谁写 | 说明 |
|---|---|---|
| `00_input.*` | ① | 原图副本（不做任何修改） |
| `case_meta.json` | ① 创建，后续补充 | 图片名、图片来源、团队、日期 |
| `01_*` | ① | 按识别手册得到的疑似病害清单（含排除的误报；小模型提示另存 01_hints） |
| `02_*` | ② | AI 复核结论，每条都标 `provenance: "AI 生成"` |
| `03_advice.json` | ③ | 1–2 条建议、不确定性、人工复核点 |
| `04_*` | ④ | 人工逐条“采纳 / 修改 / 否决”，留修改痕迹和签字 |
| `05_*` | ⑤ | 最终一页 PDF |
| `workflow_log.jsonl` | 全部 | 每一步追加一行：时间、步骤、工具、输入、输出，用于“关键步骤可追溯” |

## 规则边界

这套 skill 只用于比赛**线上阶段**（规则允许任意 AI 工具，但须完整披露）。现场阶段规则限定只能用千问办公和阿里云百炼，禁止其他 AI 助手和赛前制作的固定结果，所以现场不能使用这些 skill。

④ 的人工复核必须由队员本人完成。AI 不得替队员填写“采纳 / 修改 / 否决”或签名，规则把伪造过程记录列为取消资格的情形。
