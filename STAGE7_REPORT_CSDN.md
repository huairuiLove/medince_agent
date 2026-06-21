# 第七阶段汇报：3D 体数据 + MPR 浏览 + VISTA3D Bundle 验证

> **阶段目标**：在 Stage 5 2D 切片分割基础上，打通 NIfTI 体数据三平面 MPR 浏览、VISTA3D 真 3D 分割与全模型联调验证。  
> **承接**：Stage 5 串行分割 + Stage 6 报告流水线。  
> **实验日期**：2026-06-21  
> **本报告版本**：v1

---

## 一、承接 Stage 5~6

Stage 5 以 **2D Gallery 模式** 浏览 JPG 切片；Stage 6 消费 overlay 与截图生成报告。Stage 7 补齐 **三维体数据** 能力：

| 能力 | Stage 5 | Stage 7 |
|------|---------|---------|
| 数据形态 | JPG 切片 / 预渲染 PNG | NIfTI 体数据原生浏览 |
| 浏览模式 | Gallery slider | MPR 三平面（轴/冠/矢） |
| VISTA3D | 2D 伪体 fallback | MONAI Bundle 真 3D 推理 |
| Overlay | 2D PNG 叠加 | 3D mask 按切面合成 |
| 验证 | 单模型手测 | `test_all_models.py` 全矩阵 |

---

## 二、MPR 三平面浏览架构

```
BraTS *.nii.gz（volume_path）
  → GET /api/v1/imaging/volume/meta     → shape / spacing / slice_counts
  → GET /api/v1/imaging/volume/slice    → axis + index + overlay_path
  → export_volume_slice()               → data/imaging_cache/mpr/*.png
  → VolumeMprViewer.vue                 → 前端三平面切换 + slider
```

| 平面 | axis | 切片维度 |
|------|------|----------|
| 轴位 Axial | `axial` | Z 轴（shape[2]） |
| 冠状 Coronal | `coronal` | Y 轴（shape[1]） |
| 矢状 Sagittal | `sagittal` | X 轴（shape[0]） |

**3D mask 叠加**：VISTA3D 输出 `*_trans.nii.gz` 体 mask，`export_volume_slice()` 在对应切面提取 mask 并与底图 alpha 混合。

---

## 三、核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| 体数据 I/O | `src/imaging/volume_io.py` | `get_volume_meta` / `export_volume_slice` / 伪 NIfTI |
| VISTA3D Runner | `src/imaging/vista3d_runner.py` | MONAI Bundle 3D 推理 |
| VISTA3D Backend | `src/imaging/backends/vista3d.py` | 3D 体 / 2D 伪体 / heuristic 三级路由 |
| MPR 组件 | `frontend/src/components/imaging/VolumeMprViewer.vue` | 三平面 UI |
| 全模型测试 | `scripts/test_all_models.py` | MIMIC CT + BraTS MRI 矩阵 |

---

## 四、VISTA3D 真 3D 推理

`vista3d_runner.run_vista3d_volume()` 调用 MONAI Bundle：

```python
# 器官标签映射
ORGAN_LABELS = {
    "brain": [22],
    "liver": [1],
    "lung": [28, 29, 30, 31, 32],
}
```

**推理路径选择**（`Vista3DBackend.segment()`）：

```
volume_path 存在且为 NIfTI?
  ├─ 是 → _segment_volume_3d()     # 真 3D Bundle
  └─ 否 → image_path 为 NIfTI?
         ├─ 是 → _segment_volume_3d()
         └─ 否 → is_visual_image?
                ├─ 是 → export_pseudo_nifti_from_image() → 3D Bundle
                └─ 否 → _organ_heuristic()               # 兜底
```

**伪体数据**（2D JPG → 薄层 NIfTI）：

- `export_pseudo_nifti_from_image(depth=16, max_side=384)`
- 输出至 `data/imaging_cache/pseudo_vol/`
- 使 MIMIC CT JPG 也能走 VISTA3D Bundle 路径（CPU 首次较慢）

**输出缓存**：

```text
data/imaging_cache/vista3d/{case}/{stem}_trans.nii.gz
```

---

## 五、前端 MPR 模式

`ImagingView.vue` 根据 study 是否含 `volume_path` 自动切换：

| 模式 | 触发条件 | 组件 |
|------|----------|------|
| Gallery | 仅 `image_paths` | 内置 slider |
| MPR | 含 `volume_path` | `VolumeMprViewer` |

MPR 模式下分割请求携带：

```typescript
{
  image_path: volume_path,
  volume_path: volume_path,
  slice_axis: mprAxis,      // axial | coronal | sagittal
  slice_index: mprIndex,
  model_ids: ['vista3d', ...],
  organ: 'brain',
}
```

VISTA3D 3D 推理完成后，`stats.volume_mask_path` 回传前端，MPR 浏览自动叠加 3D mask。

---

## 六、后端 Volume API

| 接口 | 参数 | 说明 |
|------|------|------|
| `GET /api/v1/imaging/volume/meta` | `volume_path` | 体数据 shape / spacing |
| `GET /api/v1/imaging/volume/slice` | `volume_path, axis, index, overlay_path?` | MPR 切片 PNG |

路径安全：所有文件访问经 `resolve_path(".")` 根目录校验，防目录穿越。

---

## 七、全模型联调矩阵

`scripts/test_all_models.py` 覆盖：

```
数据集:  mimic_ct（MIMIC JPG） + brats_mri（BraTS NIfTI 切片）
模型:    sam2d | sam_med3d | vista3d | totalsegmentator
指标:    Status（PASS/WARN/PARTIAL/FAIL）+ mask_pixels + duration_ms + Peak RSS
```

| 状态 | 含义 |
|------|------|
| PASS | mask_pixels > 0，无 fallback |
| PARTIAL | 有 fallback / heuristic |
| WARN | mask_pixels = 0 |
| FAIL | 异常或 notes 含 `failed:` |

**运行**：

```bash
python scripts/download_models.py --all   # 首次下载权重
pip install -r requirements.txt           # 含 monai / totalsegmentator
python scripts/test_all_models.py
```

---

## 八、各模型在 3D 场景下的表现

| 模型 | MIMIC CT (JPG) | BraTS MRI (NIfTI) | 备注 |
|------|----------------|-------------------|------|
| SAM2D | PASS | WARN (低对比) | 2D 交互，MRI 部分切片 mask=0 |
| SAM-Med3D | PASS | PASS | 简化推理 pipeline |
| VISTA3D | PARTIAL (伪 3D) | PASS (真 3D) | CT 训练权重，MRI 效果受限 |
| TotalSegmentator | PARTIAL (fallback) | PARTIAL | 需 3D 体数据，2D JPG 走 fallback |

> 以上为 Demo / 研究场景预期，非临床级分割精度。

---

## 九、内存与算力

| 场景 | 峰值 RSS | 耗时（CPU） |
|------|----------|-------------|
| 单模型 2D 推理 | ~2–4 GB | 数秒 |
| VISTA3D 3D Bundle | ~6–10 GB | 首次数分钟 |
| 四模型串行 | 逐模型释放，峰值 ≈ 单模型最大 | 累加 |

**16GB 设计原则**（沿用 Stage 5）：`SegmentService` 严格串行，`release_torch()` 每轮清理。

Apple M 系列建议：VISTA3D 3D 首次推理预留 5+ 分钟；后续同 case 读缓存 mask 秒级返回。

---

## 十、七阶段总览

```
Stage 1: 方案设计 + LoRA 规划              ✅
Stage 2: Extract 原型（LoRA→API）            ✅
Stage 3: 规则引擎 review/clarify            ✅
Stage 4: 多智能体 + Vue + Docker            ✅
Stage 5: 临床 UI + 2D 影像分割              ✅
Stage 6: VLM 报告 + 段落 RAG                ✅
Stage 7: 3D MPR + VISTA3D Bundle + 联调     ✅ ← 影像链路闭环
```

**系统终态架构**：

```
Vue 前端 (/consult + /imaging + /rule-review + /cases)
  → FastAPI
      ├─ 文本侧: Extract → Rule → Multi-Agent → Clarify
      └─ 影像侧: Catalog → Segment(2D/3D) → VLM Report → RAG Q&A
```

---

## 十一、后续可选

1. MPS / CUDA 加速 VISTA3D 3D 推理
2. Embedding 向量库替代 TF-IDF RAG
3. 围术期 / 麻醉专用 Agent + 规则库
4. TotalSegmentator 真 3D 模式对接 MIMIC DICOM
5. Docker 镜像纳入 monai + 分割权重分层打包

---

## 十二、Stage 7 交付物

- [x] `volume_io` MPR 三平面导出 + 3D mask 叠加
- [x] `vista3d_runner` MONAI Bundle 3D 推理
- [x] `Vista3DBackend` 真 3D / 伪 3D / heuristic 路由
- [x] Volume meta / slice API
- [x] `VolumeMprViewer.vue` 三平面组件
- [x] `ImagingView` Gallery ↔ MPR 双模式
- [x] `test_all_models.py` 全模型验证脚本

---

## 十三、一句话总结

Stage 7 完成 MedSafe **影像链路的三维闭环**——BraTS 体数据 MPR 三平面浏览、VISTA3D 真 3D 分割、3D mask 切面叠加与四模型联调矩阵，与 Stage 1~6 文本用药安全主线共同构成完整的「影像 + 用药」临床演示系统。
