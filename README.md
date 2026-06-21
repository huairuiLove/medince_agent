# MedSafe — 多智能体用药安全审查系统

基于 MIMIC-III 临床场景，**规则引擎保底 + 大模型 API 多智能体会诊 + Vue 3 前端**。

| 阶段 | 内容 | 报告 |
|------|------|------|
| Stage 1 | 总体方案（含初版 LoRA 规划） | [STAGE1_REPORT_CSDN.md](STAGE1_REPORT_CSDN.md) |
| Stage 2 | Extract 原型（LoRA → LLM API） | [STAGE2_REPORT_CSDN.md](STAGE2_REPORT_CSDN.md) |
| Stage 3 | 规则引擎 review/clarify | [STAGE3_REPORT_CSDN.md](STAGE3_REPORT_CSDN.md) |
| Stage 4 | 多智能体 + Vue 前端 + Docker | [STAGE4_REPORT_CSDN.md](STAGE4_REPORT_CSDN.md) |

## 快速开始

### 方式一：Docker（推荐，Stage 4 工程部署）

```bash
cd medsafe_step1
docker compose up -d --build
# 前端 UI:  http://localhost:3000
# API 文档: http://localhost:8000/docs
```

### 方式二：本地开发

```bash
bash scripts/setup.sh          # 后端依赖 + 联调测试

# 终端 1
source .venv/bin/activate && medsafe serve

# 终端 2
bash scripts/dev_web.sh        # → http://localhost:5173
```

## 前端页面

| 路由 | 功能 |
|------|------|
| `/` | 系统概览、健康状态 |
| `/consult` | 多智能体会诊（Demo + 双模式输入） |
| `/rule-review` | Stage 3 纯规则审查 |
| `/cases` | Case 历史列表 |
| `/cases/:id` | Case 事件链回放 |
| `/agents` | 智能体阵容 |

## 后端 API

| 接口 | 说明 |
|------|------|
| `POST /api/v1/multi-consult` | 全流程会诊 |
| `POST /api/v1/multi-review` | 多智能体审查 |
| `POST /api/v1/extract` | LLM 结构化抽取 |
| `POST /api/v1/review` | 规则审查 |
| `GET /api/v1/case/{id}` | Case 回放 |

## LLM 配置

```env
MEDSAFE_LLM__PROVIDER=mock      # 默认离线可跑
MEDSAFE_LLM__API_KEY=sk-...       # 接入真实 API 时填写
MEDSAFE_WEB_PORT=3000
MEDSAFE_API_PORT=8000
```

## 项目结构

```text
medsafe_step1/
├── frontend/           # Vue 3 SPA
├── src/                # FastAPI + 多智能体
├── data/knowledge/     # 规则库 + formulary
├── data/demo_cases/    # 联调 case
├── docker-compose.yml  # api + web
└── STAGE1~4_REPORT_CSDN.md
```

## 测试

```bash
python scripts/run_integration_tests.py   # 19/19
cd frontend && npm run build            # 前端构建
```
