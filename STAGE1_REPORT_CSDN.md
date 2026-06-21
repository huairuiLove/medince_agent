# 第一阶段汇报：MedSafe 总体方案设计

> **项目定位**：基于 MIMIC-III 临床数据，构建医疗用药安全智能助手 MedSafe。  
> **初始技术路线**：Qwen2.5-3B-Instruct + LoRA 微调 + 规则引擎混合审查。  
> **实验日期**：2026-04-18  
> **本报告版本**：v2（延续初版设计，补充后续工程演进说明）

---

## 一、承接说明：从初版到当前

本系列四篇报告**延续同一项目脉络**：

| 报告 | 时期重点 | 状态 |
|------|----------|------|
| Stage 1（本文） | 总体方案、MIMIC 数据管线、LoRA 训练规划 | ✅ 设计完成 |
| Stage 2 | 本地 Qwen LoRA Extract 原型 | ✅ 曾完成，后迁移 API |
| Stage 3 | 规则引擎 review/clarify 骨架 | ✅ 完成 |
| Stage 4 | 去 LoRA、多智能体 API、Vue 前端、Docker | ✅ 工程落地 |

> 第四阶段报告详述为何从「本地 LoRA」转向「大模型 API + 多智能体 + 前端工程」。

---

## 二、问题定义

给定**患者上下文 + 候选用药**，系统需回答：

1. 方案是否存在安全风险？
2. 是否应阻断（block）？
3. 缺少哪些关键字段？
4. 有哪些更安全替代？

---

## 三、初版架构（Stage 1 设计时）

```
MIMIC-III CSV
  → build_mimic_samples（patient context）
  → build_sft_dataset（Extract SFT JSONL）
  → train_qwen_sft（LoRA 微调 Qwen2.5-3B）
  → infer_qwen_extract / FastAPI /api/extract
```

**设计假设**：
- Extract 任务单独 LoRA，不与 review/clarify 混训
- 先跑通「数据 → 训练 → 推理 → API」最小闭环
- 后续再扩展 review / clarify

---

## 四、MIMIC-III 数据管线设计

| 脚本 | 输入 | 输出 |
|------|------|------|
| `build_mimic_samples.py` | PATIENTS/ADMISSIONS/PRESCRIPTIONS 等 CSV | `mimiciii_patient_contexts.json` |
| `build_sft_dataset.py`（已移除） | patient contexts | extract train/val JSONL |

**字段设计**：age, gender, pregnancy_status, allergies, diagnoses, current_medications, missing_fields

---

## 五、Schema 统一设计

Stage 1 确立三类核心输出，后续阶段沿用：

- **ExtractionOutput** — 结构化抽取
- **ReviewOutput** — 风险等级、阻断、evidence
- **ClarifyOutput** — 追问 / 保守降级

Case Log 四阶段事件：`extract → review → clarify → final`（Stage 4 扩展为 7 阶段）

---

## 六、技术选型（初版 vs 现版）

| 组件 | Stage 1 规划 | Stage 4 现版 |
|------|-------------|-------------|
| Extract | Qwen LoRA 本地推理 | LLM API + Mock |
| Review | 规则引擎 | 规则 + 多 Agent |
| 部署 | 需 GPU | CPU Docker |
| 前端 | 无 | Vue 3 SPA |

---

## 七、Stage 1 交付物

- [x] 项目目录与 Schema 设计
- [x] MIMIC 样本构造脚本
- [x] Extract SFT 数据构造方案
- [x] LoRA 训练参数规划（config.yaml 原 training/lora 段）
- [x] FastAPI 接口规划

---

## 八、一句话总结

Stage 1 确立了 MedSafe 的总体目标与 LoRA 技术路线；后续 Stage 2~4 在此基座上迭代，最终在 Stage 4 完成工程化落地与架构升级。
