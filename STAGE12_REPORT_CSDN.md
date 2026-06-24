# 第十二阶段汇报：云端算力接入——远程 GPU 分割 + 影像缓存管线 + 百炼 VLM + Agent 角色隔离

> **阶段目标**：将 MedSafe 从"本地单机推理"升级为"云端算力混合架构"——新增远程 GPU 分割 Worker（AutoDL 云服务器）+ 本地/远程 Fallback 编排器（568 行核心代码）；新增两级影像分析缓存管线（574 行）避免重复 VLM/多 Agent 调用；重写 Vision LLM 客户端接入阿里云百炼 Model Studio（Qwen3-VL-Plus）；新增 Agent 角色隔离证据过滤框架（126 行）+ 6 个 Agent 重写；新增报告段落 RAG、Embedding 自适应发现、MIMIC-III I/O 模块。  
> **承接**：Stage 11（科室感知引擎 + 24 专科 Agent + KB v5 + 309 例 Benchmark）。  
> **实验日期**：2026-06-23 ~ 2026-06-24  
> **本报告版本**：v1

---

## 一、从"本地单机"到"云端混合"：升级动机

Stage 11 完成了科室感知智能（规则加权、专科 Agent、KB v5），但所有计算仍运行在本地——医学影像的 3D 分割（TotalSegmentator、BraTS 肿瘤模型）在 CPU 上动辄数分钟，VLM 临床报告生成每次都要重新调用 Qwen + DeepSeek，这在临床场景中不可接受。

Stage 12 的核心思想是：**把算力密集的任务卸载到云端 GPU，同时保证本地开发环境的完整可用性——通过 Fallback 机制实现"有云用云、无云降级"。**

| 维度 | Stage 11 终态 | Stage 12 终态 | 变化 |
|------|-------------|-------------|------|
| 影像分割算力 | 仅本地 CPU | 本地 + 远程 GPU（AutoDL） | 云端卸载 |
| 分割降级策略 | 无 | Remote → Local Fallback | 新增 |
| 影像分析缓存 | 无 | 两级缓存（VLM 分析 + 完整报告） | 新增 |
| Vision LLM | 本地 Mock / 简单 HTTP | 百炼 Model Studio（Qwen3-VL-Plus） | 重写 |
| Agent 证据过滤 | 全量传递 | 角色隔离（4 类过滤器） | 新增 |
| Embedding 发现 | 硬编码模型名 | LM Studio 自适应发现 | 新增 |
| 报告段落 RAG | 无 | TF-IDF 段落检索 + 追问 | 新增 |
| 测试文件 | 0 | 14 个（857 行） | 新增 |

---

## 二、远程 GPU 分割系统（核心功能）

### 2.1 架构概览

```
本地 MedSafe 主服务                        云端 AutoDL GPU 服务器
┌─────────────────────┐                   ┌─────────────────────────┐
│  app.py /api/v1/    │                   │  remote_worker.py       │
│  imaging/segment    │                   │  (独立 FastAPI 应用)     │
│         │           │                   │                         │
│  segment_orchestrator│                  │  POST /internal/segment │
│         │           │                   │         │               │
│  remote_client.py   │  ── HTTP ───►     │  SegmentService         │
│  (multipart upload) │  ◄── results ──   │  (CUDA GPU 推理)        │
│         │           │                   │         │               │
│  _download_artifacts│  ◄── files ────   │  _stage_artifacts       │
│  (overlay/mask 回传)│                   │  (overlay/mask 暂存)    │
└─────────────────────┘                   └─────────────────────────┘
         │                                         │
         │  fallback_to_local=true                 │  MEDSAFE_IMAGING__DEVICE=cuda
         ▼                                         │
  SegmentService (本地 CPU)                         │
                                          SSH 隧道: ssh -L 9000:...
```

### 2.2 文件结构

```
src/imaging/
├── remote_config.py          (31 行)  ─ 远程 Worker 配置读取
├── remote_client.py          (222 行) ─ HTTP 客户端（上传/下载/健康检查）
├── remote_worker.py          (215 行) ─ 远程 GPU Worker（独立 FastAPI）
├── segment_orchestrator.py   (100 行) ─ 本地/远程编排 + Fallback

scripts/
└── start_segment_worker.sh   (22 行)  ─ AutoDL 启动脚本
```

远程 GPU 核心代码总计 **568 行** Python + **22 行** Shell。

### 2.3 配置层（remote_config.py）

`remote_config.py` 从 `config.yaml` 的 `imaging.remote` 段读取配置：

```yaml
imaging:
  remote:
    enabled: false           # 总开关
    base_url: ''             # Worker 地址（SSH 隧道后为 http://127.0.0.1:9000）
    api_token: ''            # Bearer Token 认证
    timeout_seconds: 600     # 超时 10 分钟（3D 分割可能较慢）
    fallback_to_local: true  # 远程失败时降级本地
    health_cache_seconds: 30 # 健康检查缓存 30 秒
    worker:
      host: 127.0.0.1
      port: 9000
```

所有配置均可通过环境变量覆盖（`MEDSAFE_IMAGING__REMOTE__ENABLED` 等），支持 `.env` 文件注入。`remote_segment_configured()` 判断是否满足启用条件（`enabled=true` + `base_url` 非空）。

### 2.4 HTTP 客户端（remote_client.py）

`remote_client.py` 的 `run_remote_segment()` 实现了完整的远程调用链路：

**上传阶段**：使用 `httpx` 的 multipart 上传，将影像文件（PNG/JPEG/GZ）和可选的 NIfTI 体积文件以 `UploadFile` 形式发送，同时附带 JSON `metadata`（model_ids、organ、slice_axis、slice_index、point、bbox）。

**认证机制**：Bearer Token 双通道——支持 `Authorization: Bearer xxx` 标准头和 `X-Api-Token` 自定义头，Worker 端任选其一验证。

**结果回传**：Worker 返回 `job_id` + `artifact_paths` 列表，客户端通过 `_download_artifacts()` 逐个下载 overlay/mask 文件到本地 `data/imaging_cache/remote_pull/{job_id}/`，然后 `_rewrite_paths()` 递归替换结果中的远程路径为本地路径。下载完成后发送 `DELETE /internal/jobs/{job_id}` 清理远端临时文件。

**健康检查**：`check_remote_health()` 带 30 秒缓存 TTL，避免每次分割都做 HTTP 探活。`/health` 端点返回 `remote_segment_status()` 供主服务的 `/api/v1/health` 聚合使用。

### 2.5 远程 GPU Worker（remote_worker.py）

`remote_worker.py` 是一个**独立的 FastAPI 应用**（`MedSafe Segment Worker v1.0.0`），部署在 AutoDL 云服务器上：

```bash
# 在 AutoDL 服务器上运行
bash scripts/start_segment_worker.sh
# 等效于：MEDSAFE_IMAGING__DEVICE=cuda python -m src.cli segment-worker
```

Worker 暴露 4 个端点：

| 端点 | 方法 | 功能 |
|------|------|------|
| `POST /internal/segment` | POST | 接收影像上传，执行 GPU 分割，暂存产物 |
| `GET /internal/jobs/{id}/artifact` | GET | 下载指定 Job 的产物文件（overlay/mask） |
| `DELETE /internal/jobs/{id}` | DELETE | 清理 Job 临时目录 |
| `GET /health` | GET | 健康检查（返回 device 类型和可用模型列表） |

关键设计——`_stage_artifacts()`：将分割后端的输出文件（source_image、overlay_path、mask_path、volume_mask_path）复制到 `data/imaging_cache/remote_jobs/{job_id}/artifacts/`，并将结果中的路径重写为相对路径。这避免了客户端直接访问 GPU 服务器的文件系统。

安全方面：所有端点通过 `_auth_dep()` 依赖注入做 Token 校验；`download_artifact` 对路径做 `..` 和绝对路径检查，防止目录穿越。

### 2.6 编排器与 Fallback（segment_orchestrator.py）

`run_segment_with_fallback()` 是用户请求的入口，实现了三级决策：

```
1. 远程已配置？
   ├── 是 → 调用远程 Worker
   │   ├── 成功 → 返回 "已使用云端 GPU 完成分割"
   │   └── 失败 → fallback_to_local?
   │       ├── true  → 本地 CPU 执行，返回 "云端分割服务不可用，已降级为本地运算：{reason}"
   │       └── false → HTTPException 503
   └── 否 → 直接本地执行
```

返回值包含 5 个字段：`results`（分割结果列表）、`memory_peak_mb`（内存峰值）、`compute_mode`（"local" / "remote"）、`compute_message`（中文用户提示）、`fallback_from_remote`（是否发生了降级）。

`app.py` 的 `/api/v1/imaging/segment` 端点直接调用此编排器，响应中的 `SegmentResponse` 新增三个字段：

```python
class SegmentResponse(BaseModel):
    results: list
    memory_peak_mb: float
    compute_mode: str = "local"           # "local" | "remote"
    fallback_from_remote: bool = False
    compute_message: str = ""             # 中文用户提示
```

前端 `ImagingView.vue` 在分割完成后展示 `compute_message` 作为信息横幅。

### 2.7 AutoDL 部署方案

`.env.example` 中提供了完整的部署指引：

```bash
# 1. AutoDL 服务器上启动 Worker
bash scripts/start_segment_worker.sh

# 2. 本机建立 SSH 隧道
ssh -p <port> -L 9000:127.0.0.1:9000 root@connect.xxx.seetacloud.com

# 3. 本机 .env 配置
MEDSAFE_IMAGING__REMOTE__ENABLED=true
MEDSAFE_IMAGING__REMOTE__BASE_URL=http://127.0.0.1:9000
MEDSAFE_IMAGING__REMOTE__API_TOKEN=change-me
MEDSAFE_IMAGING__REMOTE__FALLBACK_TO_LOCAL=true
```

选择 AutoDL 是因为其按小时计费的 GPU 实例（A100/V100）适合间歇性的大规模影像分割任务，无需维护常驻 GPU 服务器。

---

## 三、影像分析缓存管线

### 3.1 两级缓存架构

Stage 12 引入了两级文件级缓存，避免对同一影像研究重复调用昂贵的 VLM + 多 Agent 管线：

```
L1: VLM 分析缓存 (analysis_cache)
┌──────────────────────────────────────────────┐
│ data/imaging_cache/analysis/{source}/        │
│   {patient_id}/{study_id}.json               │
│ 内容: Qwen3-VL 分析结果 + DeepSeek 综合       │
└──────────────────────────────────────────────┘
                    │
                    ▼
L2: 完整报告缓存 (report_cache)
┌──────────────────────────────────────────────┐
│ data/imaging_cache/reports/{source}/         │
│   {patient_id}/{study_id}.json               │
│ 内容: VLM + 规则审查 + 多Agent辩论 + 综合报告  │
└──────────────────────────────────────────────┘
```

| 文件 | 行数 | 功能 |
|------|------|------|
| `analysis_cache.py` | 50 | `ImagingAnalysisCacheStore`——按 study 粒度 JSON 读写 |
| `report_cache.py` | 50 | `ImagingReportCacheStore`——完整报告 JSON 读写 |
| `warm_analysis.py` | 137 | VLM 分析预热（Qwen → DeepSeek 综合） |
| `warm_report.py` | 116 | 全流程预热（VLM + 规则 + 多 Agent + 报告） |
| `case_persist.py` | 88 | 影像报告桥接 CaseStore |

缓存管线总计 **441 行**核心代码 + **133 行**预热脚本。

### 3.2 分析预热流程（warm_analysis.py）

`warm_study_analysis()` 的流程：

1. 从 `ImagingCatalog` 查找目标 study
2. `resolve_study_source_images()` 解析源影像路径——优先使用 catalog 中的预览图，无图则从 NIfTI 体积导出中心切片（`export_slice_png()`），最多取 4 张
3. 调用 Qwen3-VL（`analyze_images()`）做视觉分析，传入影像、患者摘要、模态信息
4. 可选调用 DeepSeek（`synthesize_report()`）综合 VLM 分析结果
5. 写入 `ImagingAnalysisCacheEntry` 并持久化

`get_or_run_study_analysis()` 提供 cache-or-compute 语义——有缓存直接返回，无缓存则执行分析。

### 3.3 完整报告预热（warm_report.py）

`warm_study_full_report()` 是更重量级的预热——在 L1 VLM 分析基础上，继续执行规则审查 → 多 Agent 辩论 → DeepSeek 综合 → 生成完整临床报告 → 持久化到 L2 缓存 + CaseStore。

`SOURCE_FALLBACK_CANDIDATES` 字典为不同影像来源提供模态适配的候选药物列表，确保规则审查即使在缺少真实处方时也能产出有意义的审查结果。

### 3.4 新增 API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `GET /api/v1/imaging/analysis-cache/{patient_id}/{study_id}` | GET | 读取分析 + 报告缓存 |
| `POST /api/v1/imaging/analysis-cache/warm` | POST | 触发 VLM 分析预热 |

### 3.5 批量预热脚本

`scripts/warm_imaging_analysis_cache.py`（133 行）支持命令行批量预热：

```bash
python scripts/warm_imaging_analysis_cache.py \
  --source mimic_cxr \
  --limit 10 \
  --vlm-only
```

参数：`--source`（指定影像来源）、`--limit`（限制数量）、`--force`（强制覆盖缓存）、`--clear`（清空缓存）、`--vlm-only`（仅做 VLM 分析不做完整报告）。

---

## 四、百炼 Model Studio 接入（Vision LLM 重写）

### 4.1 架构变化

`src/llm/vision_client.py`（354 行）完全重写，从简单的 HTTP 客户端升级为阿里云百炼（Model Studio）原生集成：

```
vision_client.py
├── resolve_bailian_vision_base_url()   ─ 区域感知 URL 解析
├── QwenVisionClient                    ─ Qwen3-VL-Plus 云端视觉分析
│   ├── analyze_images()                ─ 多影像 + 患者摘要 → VLM 分析
│   └── _build_messages()              ─ OpenAI 兼容消息构造
└── DeepSeekSynthesisClient             ─ DeepSeek 多源综合报告
    └── synthesize_report()            ─ VLM分析 + 规则 + Agent意见 → 综合报告
```

### 4.2 区域感知 URL 解析

`resolve_bailian_vision_base_url()` 支持 5 个阿里云区域的别名映射：

| 区域代码 | 别名 | API 端点 |
|----------|------|---------|
| `cn-beijing` | 华北2、beijing | `dashscope.aliyuncs.com` |
| `ap-southeast-1` | 新加坡、singapore | `dashscope-intl.aliyuncs.com` |
| `ap-northeast-1` | 东京、tokyo | `dashscope-intl.aliyuncs.com` |
| `eu-central-1` | frankfurt | `dashscope-intl.aliyuncs.com` |
| `us` | virginia | `dashscope-intl.aliyuncs.com` |

支持 Workspace ID——当配置了 `workspace_id` 时，URL 自动切换为 MaaS 域名格式。

### 4.3 模型升级

模型从 `qwen-vl-max-latest` 升级到 `qwen3-vl-plus`，后者在医学影像描述任务上有显著提升。新增 `VisionLLMError` 异常类（带 `status_code` 字段），支持对 API 错误做精确分类处理。

---

## 五、Agent 角色隔离与增强

### 5.1 角色证据过滤框架

`src/agents/role_evidence.py`（126 行）定义了 4 类确定性证据过滤器，确保每个 Agent 只看到属于自己职责范围的规则证据：

| 过滤器 | 角色 | 允许的 evidence category |
|--------|------|------------------------|
| `filter_pharmacist_evidence()` | 临床药师 | drug_interaction, duplicate_ingredient, ddi_* |
| `filter_attending_evidence()` | 主治医师 | clinical_scenario |
| `filter_specialist_evidence()` | 专科医师 | special_population, clinical_scenario |
| `filter_department_evidence()` | 科室专员 | priority_categories ∪ {clinical_scenario, special_population} |

关键设计：`opinion_from_evidence()` 可以纯基于规则证据生成 `AgentOpinion`，无需 LLM 调用——这为"规则已明确命中"的场景提供了确定性快速路径。

`strip_foreign_evidence_citations()` 在辩论阶段清理 Agent 引用了不属于自己角色的证据——如果检测到外来证据标记（如 `allergy:` 前缀出现在药师意见中），自动降级 `block_decision` 并在 reasons 中标注"已忽略超出本角色职责的理由"。

### 5.2 六个 Agent 重写

| Agent 文件 | 行数 | 核心变化 |
|-----------|------|---------|
| `allergy_specialist.py` | 277 | 过敏审查 Agent（全新），角色隔离 + 证据过滤 |
| `pharmacy_inventory.py` | 189 | 药房库存 Agent（全新），药品供应链审查 |
| `department_specialist.py` | 182 | 科室专员 Agent（增强），接入科室上下文引擎 |
| `internal_medicine.py` | 159 | 内科医师 Agent（增强），综合审查 |
| `specialist_router.py` | 130 | 专科路由 Agent（增强），智能分诊 |
| `clinical_pharmacist.py` | 120 | 临床药师 Agent（增强），DDI 审查增强 |

### 5.3 聊天服务患者上下文感知

`src/react/chat_service.py`（206 行）新增 `_rule_engine_kwargs()` 函数，从 `ChatRequest.patient_context` 中提取 `patient_age`、`is_pregnant`、`conditions`、`extra_drugs` 四个维度，传递给规则引擎的 `check_interactions_by_rules()`。这意味着规则降级路径（L2 RULE_FALLBACK）现在也能感知患者上下文。

`src/yuan_fallback/rule_engine.py`（479 行）对应扩展——接受患者年龄、妊娠状态、合并症、额外药物参数，使人群禁忌检查不再依赖硬编码默认值。

---

## 六、Embedding 自适应发现

`src/llm/embedding_client.py`（351 行）新增 LM Studio 模型自动发现机制：

```
配置: model = "nomic-embed-text"
  │
  ├── _fetch_api_models()     → 查询 LM Studio /models 端点
  ├── _pick_embedding_model() → 模糊匹配（配置名 → embed 关键词 → token 匹配）
  └── _resolve_api_model()    → 缓存解析结果，避免重复查询
```

`_pick_embedding_model()` 的匹配优先级：
1. 精确匹配配置的模型名
2. 包含 `embed` 关键词的模型
3. Token 匹配：`nomic`、`bge`、`e5`、`minilm` 等常见 embedding 模型标识

这解决了 LM Studio 中模型 ID 可能是完整路径（如 `nomic-ai/nomic-embed-text-v1.5`）而配置中只写短名（`nomic-embed-text`）的不匹配问题。

`src/llm/errors.py`（65 行）新增三个异常类：`DrugSearchModelNotReadyError`、`DdiModelNotReadyError`、`VisionLLMError`，使错误处理更精确。

---

## 七、报告段落 RAG

`src/reports/paragraph_rag.py`（62 行）+ `src/reports/report_qa.py`（43 行）实现了基于 TF-IDF 的报告段落追问系统：

```
医生提问: "这个结节的恶性概率如何？"
  │
  ├── ParagraphRAGIndex.search()     → TF-IDF cosine 排序，返回 top_k 相关段落
  ├── build_context()                → 段落 + 最近 5 条历史 Q&A
  └── ReportQAService.ask()          → 注入 LLM system prompt → 生成回答
```

`ParagraphRAGIndex` 使用中英文双语 tokenizer（中文字符 + 字母数字分词），构建 smoothed IDF 向量。`ReportQAService` 将检索到的段落上下文注入 LLM 的 system prompt，要求模型基于报告内容回答，并将问答记录保存为 supplement（关联 `related_paragraph_ids`）。

---

## 八、MIMIC-III 数据基础设施

`src/mimic_io.py`（66 行）新增 MIMIC-III 数据读取工具：

| 函数 | 功能 |
|------|------|
| `read_table()` | CSV/CSV.GZ 表读取，优先 gzip，支持 chunksize |
| `cxr_patient_folder()` | MIMIC-CXR-JPG 目录映射（patient_id → 影像目录） |
| `estimate_egfr_mg_dl()` | MDRD 公式 eGFR 估算（肌酐 mg/dL） |

---

## 九、测试覆盖

Stage 12 新增 **14 个测试文件**，总计 **857 行**：

| 测试文件 | 行数 | 覆盖范围 |
|---------|------|---------|
| `test_remote_segment.py` | 134 | 远程分割编排（禁用/降级/成功/不可降级 4 场景） |
| `test_imaging_analysis_cache.py` | 29 | 分析缓存读写 |
| `test_imaging_report_cache.py` | 36 | 报告缓存读写 |
| `test_role_scoped_agents.py` | 84 | 角色证据过滤 + 外来证据剥离 |
| `test_case_replay.py` | 69 | 病例回放端到端 |
| `test_allergy_specialist_agent.py` | 115 | 过敏专员 Agent 审查 |
| `test_pharmacy_inventory_agent.py` | 93 | 药房库存 Agent 审查 |
| `test_department_agents.py` | 28 | 科室 Agent 激活条件 |
| `test_vlm_image_paths.py` | 36 | VLM 影像路径校验 |
| `test_auth_department_agents.py` | 97 | 科室感知认证 + Agent 偏好 |
| `test_imaging_scope.py` | 111 | 科室级影像访问控制 |
| `test_embedding_client.py` | 25 | Embedding 模型名匹配 |

---

## 十、与已有模块的集成方式

Stage 12 延续"加法操作"原则，同时做了必要的接口适配：

| 已有模块 | 是否修改 | 集成方式 |
|----------|---------|---------|
| `src/imaging/segment_service.py` | ❌ 零改动 | 编排器调用 `segment_serial()` 不变，只是选择本地或远程执行 |
| `src/review_engine.py` | ❌ 零改动 | Agent 角色隔离在 Agent 层做，不影响规则引擎 |
| `src/knowledge_base.py` | ❌ 零改动 | 证据过滤在 `role_evidence.py` 做，不改 KB 加载 |
| `src/department/` | ❌ 零改动 | 科室上下文通过 `department_specialist.py` 接入 |
| `src/app.py` | ✅ 适配 | `/imaging/segment` 改用编排器；新增 2 个缓存端点；`/health` 聚合远程状态 |
| `src/schemas.py` | ✅ 扩展 | `SegmentResponse` 新增 3 字段；新增 `ImagingAnalysisCacheEntry` 等 |
| `config.yaml` | ✅ 新增 | `imaging.remote` 配置段（9 个配置项） |
| `.env.example` | ✅ 新增 | 5 个远程 Worker 环境变量 + SSH 隧道指引 |
| `requirements.txt` | ✅ 新增 | `python-multipart>=0.0.9`（FastAPI 文件上传） |
| 前端 `ImagingView.vue` | ✅ 适配 | 展示 `compute_message` 信息横幅 |
| 前端 `types/index.ts` | ✅ 扩展 | `SegmentResponse` 新增 3 个 TS 类型字段 |

---

## 十一、阶段总览

```
Stage 12 架构全景：

   用户请求 ─── /api/v1/imaging/segment ───┐
                                            │
                    segment_orchestrator.py  │
                        │                   │
              ┌─────────┴──────────┐        │
              ▼                    ▼        │
     remote_client.py        SegmentService │
     (HTTP + multipart)      (本地 CPU)     │
              │                             │
              ▼                             │
     remote_worker.py                       │
     (AutoDL GPU + CUDA)                    │
              │                             │
              ▼                             │
     _stage_artifacts()                     │
     (产物暂存 + 路径重写)                    │
              │                             │
              ▼                             │
     _download_artifacts()                  │
     (本地路径回写)                           │

   影像分析缓存流：
   study → resolve_source_images → Qwen3-VL (百炼) → DeepSeek 综合
         → L1 分析缓存 (JSON)
         → 规则审查 + 多Agent辩论 + 综合报告
         → L2 报告缓存 (JSON) + CaseStore

   Agent 角色隔离流：
   RuleEvidence[] → filter_pharmacist_evidence()   → 药师 Agent
                  → filter_allergy_evidence()       → 过敏 Agent
                  → filter_attending_evidence()     → 主治 Agent
                  → filter_department_evidence()    → 科室 Agent
                  → opinion_from_evidence() (确定性，无 LLM)
```

---

## 十二、Stage 12 交付物

- [x] `src/imaging/remote_config.py`（31 行，远程 Worker 配置读取）
- [x] `src/imaging/remote_client.py`（222 行，HTTP 客户端 + 健康检查 + 产物下载）
- [x] `src/imaging/remote_worker.py`（215 行，AutoDL GPU Worker 独立 FastAPI 应用）
- [x] `src/imaging/segment_orchestrator.py`（100 行，本地/远程 Fallback 编排器）
- [x] `scripts/start_segment_worker.sh`（22 行，AutoDL 启动脚本）
- [x] `src/imaging/analysis_cache.py`（50 行，L1 VLM 分析缓存）
- [x] `src/imaging/report_cache.py`（50 行，L2 完整报告缓存）
- [x] `src/imaging/warm_analysis.py`（137 行，VLM 分析预热）
- [x] `src/imaging/warm_report.py`（116 行，全流程报告预热）
- [x] `src/imaging/case_persist.py`（88 行，影像报告桥接 CaseStore）
- [x] `scripts/warm_imaging_analysis_cache.py`（133 行，批量预热脚本）
- [x] `src/llm/vision_client.py`（354 行，百炼 Qwen3-VL-Plus + DeepSeek 综合）
- [x] `src/llm/embedding_client.py`（351 行，LM Studio 自适应模型发现）
- [x] `src/llm/errors.py`（65 行，3 个新异常类）
- [x] `src/agents/role_evidence.py`（126 行，角色隔离证据过滤框架）
- [x] 6 个 Agent 重写（allergy/pharmacy/department/internal/specialist/pharmacist，共 1,057 行）
- [x] `src/react/chat_service.py`（206 行，患者上下文感知规则降级）
- [x] `src/yuan_fallback/rule_engine.py`（479 行，患者上下文扩展）
- [x] `src/reports/paragraph_rag.py`（62 行，TF-IDF 段落 RAG）
- [x] `src/reports/report_qa.py`（43 行，报告追问服务）
- [x] `src/mimic_io.py`（66 行，MIMIC-III 数据 I/O 工具）
- [x] `config.yaml`（166 行，新增 `imaging.remote` 配置段）
- [x] `.env.example`（74 行，新增 5 个远程 Worker 环境变量）
- [x] `src/cli.py`（183 行，新增 `segment-worker` 子命令）
- [x] `tests/`（14 个测试文件 / 857 行）
- [x] 前端适配（ImagingView compute_message 横幅 + SegmentResponse 类型扩展）

---

## 十三、一句话总结

Stage 12 让 MedSafe 从"本地单机推理"进化为"云端算力混合架构"——远程 GPU Worker 部署在 AutoDL 上通过 SSH 隧道接入，影像分割自动卸载到云端并在失败时降级本地 CPU；两级缓存（VLM 分析 + 完整报告）避免重复调用百炼 Qwen3-VL-Plus 和 DeepSeek；Agent 系统引入角色隔离证据过滤，6 个 Agent 重写实现职责边界清晰化——MedSafe 现在既能利用云端 GPU 的算力加速，又能在断网时完全本地运行。
