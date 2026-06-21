# 第二阶段汇报：Extract 原型（本地 LoRA → LLM API）

> **阶段目标**：实现病历文本 → 结构化 JSON 的 Extract 能力。  
> **演进路径**：本地 Qwen2.5 LoRA 微调（初版）→ LLM API 抽取（现版）。  
> **实验日期**：2026-04-22 ~ 2026-06-21

---

## 一、承接 Stage 1

Stage 1 规划了 Extract-only 原型。Stage 2 的核心任务是**跑通抽取链路**。

---

## 二、初版实现：本地 LoRA（2026-04 ~ 2026-05）

### 2.1 已完成模块（后已移除）

| 模块 | 说明 |
|------|------|
| `build_sft_dataset.py` | 从 patient context 构造 Extract SFT JSONL |
| `train_qwen_sft.py` | Qwen2.5-3B + LoRA SFT |
| `infer_qwen_extract.py` | 本地 GPU 推理 |
| `outputs/qwen25_3b_mimic_extract_lora` | LoRA 权重目录（未入库） |

### 2.2 训练配置（历史）

```bash
python -m src.train_qwen_sft \
  --model_name Qwen/Qwen2.5-3B-Instruct \
  --data_dir data/sft/mimiciii_extract \
  --output_dir outputs/qwen25_3b_mimic_extract_lora \
  --lora_r 8 --lora_alpha 16
```

### 2.3 初版局限

1. **强依赖 GPU + CUDA**，macOS 本地难以完整训练
2. **4bit 量化** 环境兼容性问题
3. Extract / Review / Clarify 若各训一套 LoRA，维护成本高
4. 权重未入库，他人无法复现完整链路

---

## 三、架构升级：LLM API Extract（现版）

Stage 4 工程落地时，Extract 改为 **OpenAI 兼容 API**：

| 模块 | 文件 |
|------|------|
| LLM 客户端 | `src/llm/client.py` |
| Extract Agent | `src/agents/extract_agent.py` |
| API | `POST /api/v1/extract` |

### 3.1 Mock 模式

`MockLLMClient` 支持无 API Key 离线运行，正则解析中文病历字段，保证 CI/Demo 可复现。

### 3.2 配置

```yaml
llm:
  provider: mock   # openai | deepseek | qwen
  api_key: ""
  model: gpt-4o-mini
```

---

## 四、Extract Schema（沿用 Stage 1）

```json
{
  "age": 67,
  "gender": "M",
  "pregnancy_status": "unknown",
  "allergies": [],
  "symptoms_or_complaints": ["胸痛"],
  "diagnoses": ["高血压"],
  "current_medications": ["warfarin"],
  "missing_fields": []
}
```

---

## 五、联调结果

| 测试项 | 初版 LoRA | 现版 API/Mock |
|--------|-----------|---------------|
| 字段抽取 | 需 GPU 权重 | S2-E1~E3 PASS |
| API 可用 | 503 无权重 | 200 正常 |
| Docker | 需 GPU 镜像 | CPU 即可 |

---

## 六、Vue 前端集成（Stage 4）

前端「多智能体会诊」页支持两种输入：

- **自然语言模式** — 调用 `/api/v1/multi-consult` 自动 Extract
- **结构化表单** — 跳过 Extract，直接审查

---

## 七、一句话总结

Stage 2 完成了 Extract 能力从 0 到 1；经历本地 LoRA 尝试后，现版以 LLM API 替代，更易部署、更易切换模型，并与 Vue 前端打通。
