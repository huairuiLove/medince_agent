# MedSafe — 多智能体用药安全审查系统

基于 MIMIC-III 临床场景，**规则引擎保底 + 大模型多智能体会诊 + ReAct 智能问答 + 影像分割与视觉报告 + Vue 3 前端**。

| 阶段 | 内容 | 报告 |
|------|------|------|
| Stage 1 | 总体方案（含初版 LoRA 规划） | [STAGE1_REPORT_CSDN.md](STAGE1_REPORT_CSDN.md) |
| Stage 2 | Extract 原型（LoRA → LLM API） | [STAGE2_REPORT_CSDN.md](STAGE2_REPORT_CSDN.md) |
| Stage 3 | 规则引擎 review/clarify | [STAGE3_REPORT_CSDN.md](STAGE3_REPORT_CSDN.md) |
| Stage 4 | 多智能体 + Vue 前端 + Docker | [STAGE4_REPORT_CSDN.md](STAGE4_REPORT_CSDN.md) |
| Stage 5 | 临床 UI + 影像 2D 分割 | [STAGE5_REPORT_CSDN.md](STAGE5_REPORT_CSDN.md) |
| Stage 6 | 视觉报告 + 段落 RAG | [STAGE6_REPORT_CSDN.md](STAGE6_REPORT_CSDN.md) |
| Stage 7 | 3D MPR + VISTA3D Bundle | [STAGE7_REPORT_CSDN.md](STAGE7_REPORT_CSDN.md) |

> **整合说明**：原 yuan-agent 已并入 MedSafe「智能问答」模块（`/chat`），支持医护专业模式与患者大众模式双角色。

---

## 环境要求

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 后端 API |
| Node.js | 18+ | 前端开发 |
| 内存 | 8 GB+（文本）；16 GB+（影像分割） | 串行加载 PyTorch 模型 |
| 磁盘 | ~10 GB 空闲 | 分割模型权重（可选） |

**默认 Mock 模式**无需任何 API Key，文本会诊、规则审查、智能问答（规则降级）均可离线运行。

---

## 快速开始（本地开发，推荐）

### 1. 安装后端

```bash
cd medince_agent

# 创建 venv、安装依赖、复制 .env、跑集成测试
bash scripts/setup.sh
```

首次安装会拉取 `torch` / `monai` 等影像依赖，耗时较长属正常。

### 2. 启动 API（终端 1）

任选一种方式（**推荐方式 A**，不依赖 `medsafe` 命令是否已安装）：

```bash
source .venv/bin/activate

# 方式 A：启动脚本（带热重载）
bash scripts/run_api.sh

# 方式 B：安装 CLI 后使用 medsafe
pip install -e .
medsafe serve --reload

# 方式 C：直接 uvicorn
python -m uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

验证：打开 http://localhost:8000/health ，应返回 `"status":"ok"`。

API 文档：http://localhost:8000/docs

### 3. 启动前端（终端 2）

```bash
bash scripts/dev_web.sh
# → http://localhost:5173
```

Vite 已将 `/api`、`/health` 代理到 `localhost:8000`，**须先启动后端**。

---

## Docker 部署（文本功能）

适合演示多智能体会诊、规则审查、智能问答；**不含分割模型权重与影像数据**。

```bash
cp .env.example .env    # 可选，默认 mock
docker compose up -d --build

# 前端 UI:  http://localhost:3000
# API 文档: http://localhost:8000/docs
```

Docker 内 `/imaging` 页面可访问，但无本地模型与 BraTS/MIMIC 数据时分割功能不可用。完整影像能力请用本地开发方式并执行下方「影像模块」步骤。

---

## 影像模块（可选）

影像分割、MPR 浏览、视觉报告需在本地额外准备：

### 1. 下载模型权重

```bash
source .venv/bin/activate
python scripts/download_models.py --all
# 权重写入 models/（已在 .gitignore，不入库）
```

| 模型 | 目录 |
|------|------|
| VISTA3D | `models/vista3d/` |
| SAM-Med3D | `models/SAM-Med3D/` |
| SAM2D (MedSAM) | `models/SAM2D/` |
| TotalSegmentator | `models/totalsegmentator/` |

### 2. 放置影像数据

```text
data/mimic/{patient_id}/{study_id}/*.jpg      # MIMIC CT 切片
data/brats2024/{case_id}/*.nii.gz             # BraTS MRI 体数据（不含 seg）
```

目录结构见 `data/mimic/.gitkeep` 与 `data/brats2024/.gitkeep`。无数据时 `/imaging` 显示空列表，不影响其他页面。

### 3. 验证分割链路

```bash
python scripts/test_all_models.py
```

---

## 前端页面

| 路由 | 功能 |
|------|------|
| `/` | 系统概览、健康状态 |
| `/consult` | 多智能体会诊（Demo + 自然语言 / 结构化表单） |
| `/chat` | 智能问答（ReAct + Graph RAG，医护 / 患者双角色） |
| `/rule-review` | 纯规则审查 |
| `/imaging` | 影像浏览、分割、视觉报告、段落 RAG 追问 |
| `/cases` | Case 历史列表 |
| `/cases/:id` | Case 事件链回放 |
| `/agents` | 智能体阵容说明 |

---

## 配置

复制并按需修改环境变量：

```bash
cp .env.example .env
```

| 变量 | 说明 | 默认 |
|------|------|------|
| `MEDSAFE_LLM__PROVIDER` | 会诊 Extract / Agent | `mock` |
| `MEDSAFE_LLM__API_KEY` | 上述 LLM Key | 空 |
| `MEDSAFE_CHAT__PROVIDER` | 智能问答 ReAct | `mock` |
| `MEDSAFE_CHAT__API_KEY` | 问答 LLM Key（可填 DeepSeek） | 空 |
| `MEDSAFE_VISION_LLM__PROVIDER` | 影像 VLM（Qwen3-VL） | `mock` |
| `MEDSAFE_VISION_LLM__API_KEY` | 通义 DashScope Key | 空 |
| `MEDSAFE_DEEPSEEK__API_KEY` | 报告综合合成 | 空 |
| `MEDSAFE_AGENTS__RULE_STRICT` | 高风险规则不可被 LLM 覆盖 | `true` |
| `MEDSAFE_SERVER__PORT` | API 端口 | `8000` |

环境变量使用双下划线表示嵌套，例如 `MEDSAFE_LLM__PROVIDER` → `config.yaml` 中的 `llm.provider`。也可直接编辑 [config.yaml](config.yaml)。

**接入 DeepSeek 示例**（会诊 + 问答）：

```env
MEDSAFE_LLM__PROVIDER=openai
MEDSAFE_LLM__API_KEY=sk-...
MEDSAFE_LLM__BASE_URL=https://api.deepseek.com/v1
MEDSAFE_LLM__MODEL=deepseek-chat

MEDSAFE_CHAT__PROVIDER=deepseek
MEDSAFE_CHAT__API_KEY=sk-...
```

---

## 后端 API 概览

### 用药安全

| 接口 | 说明 |
|------|------|
| `POST /api/v1/multi-consult` | 全流程会诊（Extract → Rule → Agent → 仲裁） |
| `POST /api/v1/multi-review` | 多智能体审查（跳过 Extract） |
| `POST /api/v1/extract` | LLM 结构化抽取 |
| `POST /api/v1/review` | 规则审查 |
| `POST /api/v1/clarify` | 追问 / 保守降级 |
| `GET /api/v1/case/{id}` | Case 回放 |
| `GET /api/v1/cases` | Case 列表 |

### 智能问答

| 接口 | 说明 |
|------|------|
| `POST /api/v1/chat/stream` | SSE 流式问答（`role`: `doctor` / `patient`） |
| `GET /api/v1/chat/system-state` | 降级状态（L0~L3） |
| `POST /api/v1/drug/info` | 药品图谱查询 |

MCP 工具服务由 API 启动时自动拉起子进程（`python -m src.mcp.mcp_server`），**无需单独启动**。

### 影像与报告

| 接口 | 说明 |
|------|------|
| `GET /api/v1/imaging/studies` | 影像 study 列表 |
| `POST /api/v1/imaging/segment` | 串行分割（多模型） |
| `GET /api/v1/imaging/volume/meta` | NIfTI 体数据元信息 |
| `GET /api/v1/imaging/volume/slice` | MPR 切片 PNG |
| `POST /api/v1/imaging/report/generate` | 生成 7 段临床报告 |
| `POST /api/v1/imaging/report/ask` | 段落 RAG 追问 |

---

## CLI

安装 editable 包后可使用：

```bash
pip install -e .

medsafe serve --reload   # 启动 API
medsafe test             # 集成测试
medsafe info             # 打印 LLM / 配置信息
medsafe demo-data        # 生成 Demo 数据
```

未安装 CLI 时，用 `bash scripts/run_api.sh` 与 `python scripts/run_integration_tests.py` 等价替代。

---

## 测试

```bash
source .venv/bin/activate

# 用药安全集成测试（含多轮辩论 S4-D1~D5，24 项）
python scripts/run_integration_tests.py

# 影像分割全模型矩阵（需模型权重 + 影像数据）
python scripts/test_all_models.py

# 前端生产构建
cd frontend && npm install && npm run build
```

---

## 项目结构

```text
medince_agent/
├── frontend/              # Vue 3 + TypeScript + Vite
├── src/
│   ├── agents/            # 多智能体（药师、内科、过敏、药房、专科、主席）
│   ├── debate/            # 多轮辩论 + Critic + Moderator + Safety Panel
│   ├── react/             # ReAct 循环 + 智能问答
│   ├── graph_rag/         # 药品知识图谱检索
│   ├── mcp/               # MCP 工具服务（子进程）
│   ├── yuan_fallback/     # 四级降级兜底
│   ├── imaging/           # 影像目录、分割、MPR
│   ├── reports/           # 视觉报告 + 段落 RAG
│   ├── llm/               # LLM / VLM 客户端
│   └── app.py             # FastAPI 入口
├── data/
│   ├── knowledge/         # 规则库 + drug_kg.json
│   ├── demo_cases/        # 联调用例
│   ├── mimic/             # MIMIC CT（自行放置）
│   └── brats2024/         # BraTS MRI（自行放置）
├── models/                # 分割权重（download_models.py 下载）
├── scripts/               # setup / run_api / dev_web / 测试
├── config.yaml
├── docker-compose.yml
└── STAGE1~7_REPORT_CSDN.md
```

---

## 常见问题

**`medsafe: command not found`**  
`setup.sh` 只安装 `requirements.txt`，未注册 CLI。执行 `pip install -e .`，或改用 `bash scripts/run_api.sh`。

**前端报「后端未连接」**  
先确认终端 1 中 API 已启动，且 http://localhost:8000/health 可访问。

**`/imaging` 无 study**  
检查 `data/mimic/` 或 `data/brats2024/` 是否已放入数据（见 `.gitkeep` 说明）。

**分割报错或极慢**  
确认已运行 `python scripts/download_models.py --all`；VISTA3D 3D 推理在 CPU 上首次需数分钟；16 GB 机器请只勾选 1~2 个模型。

**Docker 中影像不可用**  
默认镜像未打包模型与影像数据，请使用本地开发 + 上述影像模块步骤。

---

## 系统架构

```
MedSafe v3
├── 多智能体会诊 (/consult)     — 规则 → 多轮辩论 + Critic → Moderator → 主席仲裁
├── 智能问答 (/chat)            — ReAct + MCP + Graph RAG + 四级降级
├── 规则审查 (/rule-review)     — 确定性规则引擎
├── 影像与会诊 (/imaging)       — 分割 → VLM 报告 → 段落 RAG
└── 病例回放 (/cases)           — Case 事件链 JSON 持久化
```

多轮辩论架构见 [docs/DEBATE_ARCHITECTURE.md](docs/DEBATE_ARCHITECTURE.md)，参考文献见 [docs/REFERENCES.md](docs/REFERENCES.md)。
