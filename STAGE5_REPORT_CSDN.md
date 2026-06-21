# 第五阶段汇报：临床风 UI + 影像分割基础链路

> **阶段目标**：将 MedSafe 从纯文本用药审查扩展为「影像 + 用药」一体化临床演示系统。  
> **承接**：Stage 4 多智能体 + Vue 前端 + Docker 工程基座。  
> **实验日期**：2026-06-21  
> **本报告版本**：v1

---

## 一、承接 Stage 4

Stage 4 完成了文本侧全流程（Extract → Rule Gate → 多 Agent → 仲裁 → Clarify）。Stage 5 在此基础上新增 **医学影像浏览与 2D 分割** 能力，并将前端视觉语言从 SaaS 风格调整为 **医院信息系统（HIS）临床风**。

| 报告 | 时期重点 | 状态 |
|------|----------|------|
| Stage 1~4 | 用药安全主线 | ✅ 完成 |
| Stage 5（本文） | 临床 UI + 影像目录 + 串行 2D 分割 | ✅ 完成 |
| Stage 6 | VLM 报告 + 段落 RAG 追问 | ✅ 完成 |
| Stage 7 | 3D 体数据 + MPR + VISTA3D Bundle | ✅ 完成 |

---

## 二、问题定义

Stage 5 需回答：

1. 如何在 **16GB 内存** 约束下串行加载多个分割模型？
2. 如何统一浏览 **MIMIC CT（JPG）** 与 **BraTS MRI（NIfTI）** 两类数据源？
3. 如何让前端具备 **临床系统** 而非消费级 App 的视觉气质？
4. 如何为后续 VLM 报告提供 **overlay + 截图** 输入？

---

## 三、临床风 UI 改造

Stage 4 前端主色为青绿 `#0d9488`，偏健康 App 风格。Stage 5 统一调整为临床蓝系：

| 元素 | Stage 4 | Stage 5 |
|------|---------|---------|
| 主色 | `#0d9488` 青绿 | `#1565c0` 医疗蓝 |
| 侧边栏 | `#0f172a` + emoji | `#1e3a5f` 无 emoji |
| 字体 | DM Sans | Source Sans 3 |
| 背景 | 渐变 hero | 近白 `#f0f4f8` |

**改动文件**：

- `frontend/src/styles/global.css` — CSS 变量与按钮样式
- `frontend/src/components/layout/MainLayout.vue` — 侧边栏导航
- `frontend/src/views/HomeView.vue` — 概览页增加「影像会诊」入口

新增路由 `/imaging` → `ImagingView.vue`。

---

## 四、影像目录与数据管线

```
data/mimic/{patient}/{study}/*.jpg     → MIMIC CT 切片图
data/brats2024/{case}/*.nii.gz         → BraTS MRI 体数据
         ↓
ImagingCatalog.list_studies()
         ↓
ImagingStudyItem（study_id / modality / image_paths / volume_path）
         ↓
data/imaging_cache/catalog/            → NIfTI → PNG 切片缓存
```

| 模块 | 文件 | 职责 |
|------|------|------|
| 目录扫描 | `src/imaging/catalog.py` | MIMIC + BraTS 自动发现 |
| 体数据 I/O | `src/imaging/volume_io.py` | NIfTI 切片导出、灰度归一化 |
| 模型注册 | `src/imaging/registry.py` | 4 模型元数据与器官支持 |
| 串行调度 | `src/imaging/segment_service.py` | 逐模型加载 → 推理 → 卸载 |
| 内存监控 | `src/imaging/memory_monitor.py` | RSS 峰值追踪 |

---

## 五、四模型串行分割架构

**设计约束**：Apple Silicon / 16GB 环境无法同时加载多个 PyTorch 模型，采用 **Serial Load → Infer → Unload** 策略。

| model_id | 名称 | 模态 | 说明 |
|----------|------|------|------|
| `sam2d` | SAM2D (MedSAM) | CT/MRI/XR | 2D 点/框交互分割 |
| `sam_med3d` | SAM-Med3D | CT/MRI | 医学 2D 切片分割 |
| `vista3d` | VISTA3D | CT/MRI | MONAI 交互式器官分割 |
| `totalsegmentator` | TotalSegmentator | CT | nnU-Net 全器官（2D fast 模式） |

```
POST /api/v1/imaging/segment
  → SegmentService.segment_serial(image_path, model_ids[])
      → for each model_id:
            unload_active()
            backend.segment(...)
            backend.unload()
            release_torch()
  → SegmentResponse（overlay_path / stats / memory_mb / duration_ms）
```

**权重目录**（`models/`）：

```text
models/
├── SAM2D/medsam_vit_b.pth
├── SAM-Med3D/*.pth
├── vista3d/          # MONAI Bundle 0.5.11
└── totalsegmentator/ # nnU-Net 权重（首次推理拉取）
```

下载脚本：`python scripts/download_models.py --all`

---

## 六、后端 API（Stage 5 新增）

| 接口 | 说明 |
|------|------|
| `GET /api/v1/imaging/studies` | 影像 study 列表 |
| `GET /api/v1/imaging/models` | 可用分割模型 |
| `GET /api/v1/imaging/file` | 静态影像文件服务 |
| `POST /api/v1/imaging/segment` | 串行分割 |
| `POST /api/v1/imaging/screenshot` | 保存医生截图 |

---

## 七、前端「影像与会诊」页（Gallery 模式）

`ImagingView.vue` Stage 5 核心功能：

- **Study 选择器** — MIMIC CT / BraTS MRI 切换
- **切片浏览** — JPG gallery 层位 slider
- **模型多选** — 勾选 1~4 模型串行推理
- **Overlay 预览** — 分割结果叠加显示
- **截图采集** — Canvas 截取当前视图 → 后端持久化

---

## 八、依赖与配置

`requirements.txt` 新增（Stage 5 注释段）：

```text
nibabel>=5.2.0
torch>=2.2.0
totalsegmentator>=2.3.0
monai>=1.4.0
huggingface_hub>=0.23.0
```

`config.yaml` 新增 `paths.models_dir`、`paths.reports_dir` 段，为 Stage 6 报告存储预留。

---

## 九、已知限制

| 限制 | 说明 |
|------|------|
| TotalSegmentator + 2D JPG | nnU-Net 需 3D 体数据，2D 输入走伪 NIfTI fallback |
| SAM2D + 低对比 MRI | BraTS 部分切片 mask=0 |
| CPU 推理 | VISTA3D Bundle 首次推理 CPU 需数分钟 |
| 云端 VLM | Stage 5 仅搭建分割链路，报告生成见 Stage 6 |

---

## 十、Stage 5 交付物

- [x] 临床风 UI 全局样式与导航改造
- [x] `ImagingCatalog` MIMIC + BraTS 双数据源
- [x] 4 模型 Backend + 串行 `SegmentService`
- [x] 内存监控与模型权重下载脚本
- [x] `/imaging` 前端页（Gallery + 分割 + 截图）
- [x] Imaging 相关 FastAPI 路由

---

## 十一、一句话总结

Stage 5 为 MedSafe 补上 **影像分割基础链路**：临床风 UI、双数据源目录、四模型串行推理与截图采集——为 Stage 6 视觉语言报告与 Stage 7 三维 MPR 浏览奠定输入侧能力。
