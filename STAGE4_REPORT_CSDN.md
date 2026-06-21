# 第四阶段汇报：工程落地 — 多智能体 API + Vue 前端 + Docker

> **项目定位**：MedSafe 从「本地 LoRA 实验」升级为「可部署工程产品」。  
> **版本**：v2.0.0  
> **实验日期**：2026-06-21  
> **承接**：Stage 1~3 设计 + 原 Stage 4 规则联调（42/42 PASS）

---

## 一、从本地模型到工程落地：为什么升级

| 问题（LoRA 路线） | 工程化方案 |
|-------------------|-----------|
| 需 GPU/CUDA 训练与推理 | LLM API + Mock 离线 |
| 三套 LoRA（extract/review/clarify）维护成本高 | 统一 API 客户端 + Prompt |
| 无可视化界面 | Vue 3 完整前端 |
| 部署复杂 | Docker Compose 一键启动 |

**架构终态**：

```
Vue 前端 (port 3000)
  → nginx 反代 /api
  → FastAPI (port 8000)
      → LLM Extract
      → Rule Gate
      → 5 Agent 并行
      → 主席仲裁
      → Clarify
      → Case Log
```

---

## 二、多智能体编排（Stage 4 核心）

### 2.1 智能体

| agent_id | 名称 | 职责 |
|----------|------|------|
| clinical_pharmacist | 临床药师 | DDI、剂量 |
| internal_medicine | 内科主治 | 适应证 |
| allergy_specialist | 过敏专员 | 交叉过敏 |
| pharmacy_inventory | 药房库管 | 库存/formulary |
| specialist | 专科医生 | 动态激活 |
| chief_reviewer | 会诊主席 | 仲裁 |
| coordinator | 信息协调员 | Clarify |

### 2.2 关键 API

- `POST /api/v1/multi-consult` — 全流程
- `POST /api/v1/multi-review` — 跳过 Extract
- `GET /api/v1/agents` — 智能体列表

---

## 三、Vue 3 前端（本次新增）

### 3.1 技术栈

- Vue 3 + TypeScript + Composition API
- Vue Router 4
- Vite 6 构建

### 3.2 页面

| 路由 | 页面 | 功能 |
|------|------|------|
| `/` | 概览 | 健康检查、四阶段说明 |
| `/consult` | 多智能体会诊 | Demo 载入、双模式输入、结果展示 |
| `/rule-review` | 规则审查 | Stage 3 纯规则 |
| `/cases` | Case 列表 | 历史记录 |
| `/cases/:id` | Case 回放 | 事件链 + 专家意见 |
| `/agents` | 智能体 | 阵容说明 |

### 3.3 组件

- `AgentOpinionCard` — 专家意见卡片
- `RuleEvidencePanel` — 规则 evidence
- `ClarifyPanel` — 追问/保守降级
- `RiskBadge` — 风险等级

### 3.4 目录

```text
frontend/
├── src/views/          # 6 个页面
├── src/components/     # 布局 + 会诊组件
├── src/api/medsafe.ts  # API 封装
├── src/data/demoCases.ts
├── Dockerfile          # nginx 生产镜像
└── nginx.conf          # 反代 /api → backend
```

---

## 四、Docker 部署

```bash
docker compose up -d --build
# 前端: http://localhost:3000
# API:  http://localhost:8000/docs
```

| 服务 | 镜像 | 端口 |
|------|------|------|
| api | medsafe-api:2.0.0 | 8000 |
| web | medsafe-web:2.0.0 | 3000 |

---

## 五、本地开发

```bash
# 终端 1：后端
medsafe serve

# 终端 2：前端（代理 /api → 8000）
bash scripts/dev_web.sh
# → http://localhost:5173
```

---

## 六、联调结果（v2 全量）

```
Stage 3 规则:  5/5 PASS
Stage 2 Extract: 3/3 PASS
Stage 4 多智能体: 11/11 PASS
─────────────────────────
合计: 19/19 PASS (100%)
```

Vue 构建：`npm run build` ✓

---

## 七、Case Log 扩展

| 阶段 | 说明 |
|------|------|
| extract | LLM 结构化 |
| rule_gate | 规则预筛 |
| agent_review | 多 Agent 并行 |
| arbitration | 主席仲裁 |
| clarify | 追问/降级 |
| final | 最终建议 |

---

## 八、四阶段总览

```
Stage 1: 方案设计 + LoRA 规划           ✅
Stage 2: Extract 原型（LoRA→API）       ✅
Stage 3: 规则引擎（原42项联调）          ✅
Stage 4: 多智能体 + Vue + Docker        ✅ ← 工程落地
```

---

## 九、后续可选

1. 接入 DeepSeek / 通义千问 API
2. Agent Round 2 辩论
3. 规则库扩展（DrugBank/TWOSIDES）
4. 用户认证与审计

---

## 十、一句话总结

Stage 4 将 MedSafe 从「本地 LoRA 实验项目」升级为**带 Vue 前端、Docker 部署、多智能体 API 的完整工程**——四篇报告一脉相承，本阶段为最终交付形态。
