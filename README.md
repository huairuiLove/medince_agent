# MedSafe — 多智能体用药安全审查系统

基于 MIMIC-III 临床场景，**院级药库（PIS CSV）+ CPOE 审查 + 规则引擎保底 + 多轮辩论会诊 + ReAct 智能问答 + 影像分割与视觉报告 + Vue 3 前端**。

> **产品重心**：用药安全（药库 / 术语 / 规则 / 会诊）是进院主链路；影像模块用于辅助诊断演示，可选部署。

> **整合说明**：原 yuan-agent 已并入 MedSafe「智能问答」模块（`/chat`），支持医护专业模式与患者大众模式双角色。

---

## 环境要求

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 后端 API |
| Node.js | 18+ | 前端开发 |
| 内存 | 8 GB+（文本）；16 GB+（影像分割） | 串行加载 PyTorch 模型 |
| 磁盘 | ~10 GB 空闲 | 分割模型权重（可选） |

**默认 Mock 模式**无需任何 API Key，文本会诊、规则审查、CPOE 药库审查、智能问答（规则降级）均可离线运行。

---

## 快速开始（本地开发，推荐）

### 1. 安装后端

```bash
cd medince_agent

# 创建 venv、安装依赖、复制 .env、跑集成测试
bash scripts/setup.sh
```

首次安装会拉取 `torch` / `monai` 等影像依赖，耗时较长属正常。

### 2. 导入演示院目录（药库，推荐）

API 启动时会自动导入 `data/hospital/formulary_demo.csv`（**1120 条**演示品种）。也可手动同步：

```bash
source .venv/bin/activate

# 生成 / 刷新演示 CSV（1120+ 行）
python scripts/build_demo_formulary.py

# 导入 SQLite 药库
python scripts/sync_formulary.py --csv data/hospital/formulary_demo.csv
```

验证：`curl -s http://localhost:8000/api/v1/drug-catalog/stats | python -m json.tool`

### 3. 启动 API（终端 1）

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

验证：打开 http://localhost:8000/health ，应返回 `"status":"ok"` 且含 `drug_catalog.total_drugs`。

API 文档：http://localhost:8000/docs

### 4. 启动前端（终端 2）

```bash
bash scripts/dev_web.sh
# → http://localhost:5173
```

Vite 已将 `/api`、`/health` 代理到 `localhost:8000`，**须先启动后端**。

---

## 院级药库与 CPOE 对接

MedSafe 支持 **PIS 药事系统 CSV 导出** 作为院目录数据源（试点医院最常见方式）。

### CSV 格式

模板见 `data/hospital/formulary_sample.csv`（最小样例）与 `data/hospital/formulary_demo.csv`（**1120 行演示库**）。

| 必填列 | 说明 |
|--------|------|
| `hospital_drug_id` | 院内药品码（CPOE 医嘱主键） |
| `generic_name_cn` | 中文通用名 |
| `generic_name_en` | 英文 INN（DDI 规则对齐） |
| `trade_name_cn` | 商品名 |
| `strength` / `dosage_form` / `route` | 规格、剂型、途径 |
| `in_formulary` / `in_stock` | `1/0` 或 `是/否` |
| `rxnorm_rxcui` / `atc_code` | 可选，术语映射 |

中英文表头均支持（如 `院内药品码`、`通用名`），详见 `src/drug_catalog/csv_import.py`。

### 同步与配置

```bash
#  nightly / 手动全量同步
python scripts/sync_formulary.py --csv /path/to/hospital_export.csv

# 或通过 API 热更新（无需重启）
curl -X POST http://localhost:8000/api/v1/drug-catalog/sync \
  -H 'Content-Type: application/json' \
  -d '{"csv_path": "data/hospital/formulary_demo.csv"}'
```

[config.yaml](config.yaml) 相关项：

```yaml
drug_catalog:
  db_path: "data/hospital/formulary.db"
  formulary_path: "data/hospital/formulary_demo.csv"
  auto_import_on_startup: true
```

### CPOE 实时审查示例

```bash
curl -X POST http://localhost:8000/api/v1/cpoe/medication-review \
  -H 'Content-Type: application/json' \
  -d '{
    "encounter_id": "ENC001",
    "patient": {"patient_id": "P001", "age": 72, "gender": "M", "allergies": []},
    "orders": [{"order_id": "O1", "hospital_drug_id": "H-DEMO-00006"}],
    "existing_medications": [{"hospital_drug_id": "H-DEMO-00001", "name": "华法林钠 2.5mg"}]
  }'
```

华法林 + 布洛芬应返回 `"overall_status": "blocked"` 及 DDI 告警。

---

## Docker 部署（文本 + 药库）

适合演示多智能体会诊、CPOE 审查、规则审查、智能问答；**不含分割模型权重与影像数据**。

```bash
cp .env.example .env    # 可选，默认 mock
docker compose up -d --build

# 前端 UI:  http://localhost:3000
# API 文档: http://localhost:8000/docs
```

将医院 CSV 挂载到容器内并设置 `MEDSAFE_DRUG_CATALOG__FORMULARY_PATH` 即可替换演示药库。Docker 内 `/imaging` 无本地模型与数据时分割不可用。

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

目录结构见 `data/mimic/.gitkeep` 与 `data/brats2024/.gitkeep`。无数据时 `/imaging` 显示空列表，不影响用药功能。

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
| `MEDSAFE_DRUG_CATALOG__FORMULARY_PATH` | 院目录 CSV 路径 | `data/hospital/formulary_demo.csv` |
| `MEDSAFE_DRUG_CATALOG__AUTO_IMPORT_ON_STARTUP` | 启动时自动导入空库 | `true` |
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

### 用药安全与会诊

| 接口 | 说明 |
|------|------|
| `POST /api/v1/multi-consult` | 全流程会诊（Extract → Rule → 辩论 → 仲裁） |
| `POST /api/v1/multi-review` | 多智能体审查（跳过 Extract） |
| `POST /api/v1/extract` | LLM 结构化抽取 |
| `POST /api/v1/review` | 规则审查 |
| `POST /api/v1/clarify` | 追问 / 保守降级 |
| `GET /api/v1/case/{id}` | Case 回放 |
| `GET /api/v1/cases` | Case 列表 |

### 院级药库 / CPOE

| 接口 | 说明 |
|------|------|
| `POST /api/v1/cpoe/medication-review` | CPOE 结构化医嘱审查（院内码 + 分级告警） |
| `POST /api/v1/drug-catalog/sync` | 从 CSV 同步院目录 |
| `GET /api/v1/drug-catalog/stats` | 药库统计 / 最近同步版本 |
| `GET /api/v1/drug-catalog/drugs/{id}` | 按院内码查询 |
| `GET /api/v1/drug-catalog/search?q=` | 模糊搜索 |

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

## CLI 与脚本

安装 editable 包后可使用：

```bash
pip install -e .

medsafe serve --reload   # 启动 API
medsafe test             # 集成测试
medsafe info             # 打印 LLM / 配置信息
medsafe demo-data        # 生成 Demo 数据
```

| 脚本 | 说明 |
|------|------|
| `bash scripts/run_api.sh` | 启动 API（等价 `medsafe serve`） |
| `bash scripts/dev_web.sh` | 启动前端 |
| `bash scripts/setup.sh` | 一键环境安装 |
| `python scripts/build_demo_formulary.py` | 生成 1120 行演示院目录 CSV |
| `python scripts/sync_formulary.py --csv …` | 导入 PIS CSV 到 SQLite |
| `python scripts/run_integration_tests.py` | 集成测试（30 项） |

---

## 测试

```bash
source .venv/bin/activate

# 用药安全 + 药库 + CPOE + 辩论（30 项）
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
│   ├── drug_catalog/      # 院目录 CSV 导入、术语、CPOE ReviewFacade
│   ├── agents/            # 多智能体（药师、内科、过敏、药房库管、专科、主席）
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
│   ├── hospital/          # formulary_demo.csv（1120 行）、formulary.db（本地生成）
│   ├── knowledge/         # 规则库 + drug_kg.json
│   ├── demo_cases/        # 联调用例
│   ├── mimic/             # MIMIC CT（自行放置）
│   └── brats2024/         # BraTS MRI（自行放置）
├── models/                # 分割权重（download_models.py 下载）
├── scripts/               # setup / run_api / sync_formulary / 测试
├── docs/                  # DEBATE_ARCHITECTURE.md、REFERENCES.md
├── config.yaml
└── docker-compose.yml
```

---

## 常见问题

**`medsafe: command not found`**  
`setup.sh` 只安装 `requirements.txt`，未注册 CLI。执行 `pip install -e .`，或改用 `bash scripts/run_api.sh`。

**前端报「后端未连接」**  
先确认终端 1 中 API 已启动，且 http://localhost:8000/health 可访问。

**药库为空 / CPOE 报 UNRESOLVED_DRUG**  
执行 `python scripts/sync_formulary.py --csv data/hospital/formulary_demo.csv`，或确认 `config.yaml` 中 `drug_catalog.auto_import_on_startup: true`。

**CPOE 演示华法林+布洛芬**  
演示库中华法林为 `H-DEMO-00001`，布洛芬为 `H-DEMO-00006`（重新生成 CSV 后 ID 可能变化，以 `formulary_demo.csv` 为准）。

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
├── 院级药库 (PIS CSV → SQLite)   — 术语解析、库存/目录校验
├── CPOE 审查 API                 — 结构化医嘱、分级告警（hard_stop / warning）
├── 多智能体会诊 (/consult)       — 规则 → 多轮辩论 + Critic → Moderator → 主席仲裁
├── 智能问答 (/chat)              — ReAct + MCP + Graph RAG + 四级降级
├── 规则审查 (/rule-review)         — 确定性规则引擎
├── 影像与会诊 (/imaging)         — 分割 → VLM 报告 → 段落 RAG（可选）
└── 病例回放 (/cases)             — Case 事件链 JSON 持久化
```

多轮辩论架构见 [docs/DEBATE_ARCHITECTURE.md](docs/DEBATE_ARCHITECTURE.md)，参考文献见 [docs/REFERENCES.md](docs/REFERENCES.md)。
