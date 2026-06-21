# MedSafe 参考文献与对标项目

> 本目录文档说明 MedSafe 多轮辩论架构的理论基础与开源对标。  
> 架构细节见 [DEBATE_ARCHITECTURE.md](./DEBATE_ARCHITECTURE.md)。

---

## 一、MedSafe 已借鉴 / 已实现

| 来源 | 机制 | MedSafe 模块 |
|------|------|-------------|
| [ClinicalPilot](https://github.com/laksh-ya/ClinicalPilot) | 2~3 轮 Debate + Critic + Safety Panel | `src/debate/debate_engine.py`, `critic_agent.py`, `safety_panel.py` |
| [MDAgents](https://github.com/mitmedialab/MDAgents) (NeurIPS 2024) | Moderator 组讨论汇总 | `src/debate/moderator.py` |
| Stage 3 规则引擎 | 确定性 DDI / 过敏 / 妊娠 | `src/review_engine.py` + `rule_strict` |
| [SafeRx-Agent](https://arxiv.org/html/2605.29146v2) | Critic-Revision + Safety Verifier | 部分实现（Safety Panel + Critic） |
| [MedCoAct](https://arxiv.org/html/2510.10461) | 置信度反思 | `confidence_threshold` 门控 |

---

## 二、用药安全 / 多智能体（论文）

| 文献 | 链接 | 要点 |
|------|------|------|
| **SafeRx-Agent** | [arXiv:2605.29146](https://arxiv.org/html/2605.29146v2) | MIMIC-III/IV；专科 Agent + Global Critique + Safety Verifier |
| **MedCoAct** | [arXiv:2510.10461](https://arxiv.org/html/2510.10461) | 医生-药师双 Agent；confidence-aware reflection |
| **MDAgents** | [NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/90d1fc07f46e31387978b88e7e057a31-Paper-Conference.pdf) | 复杂度路由 + Moderator；+11.8% with RAG |
| **MDTeamGPT** | [arXiv:2503.13856](https://arxiv.org/pdf/2503.13856) | 多轮 MDT + Lead Physician 残差压缩 |
| **MedSentry** | [arXiv:2505.20824](https://arxiv.org/pdf/2505.20824) | 多 Agent 安全风险与信息污染 |
| **Trust but Verify** | [arXiv:2606.14149](https://arxiv.org/html/2606.14149) | Safety Auditor + 最多 3 次 retry |
| **MIMIC-III** | Johnson et al., Sci Data 2016 | 数据集与方法学引用 |

---

## 三、开源项目（有代码）

| 项目 | GitHub | 辩论 | 置信度 | 用药安全 |
|------|--------|:----:|:------:|:--------:|
| **ClinicalPilot** | [laksh-ya/ClinicalPilot](https://github.com/laksh-ya/ClinicalPilot) | 2~3 轮 + Critic | 共识/人工 flag | RxNorm + DrugBank |
| **MDAgents** | [mitmedialab/MDAgents](https://github.com/mitmedialab/MDAgents) | Moderator 组讨论 | 复杂度路由 | 通用医学 QA |
| **MDTeamGPT** | [KaiChenNJ/MDTeamGPT](https://github.com/KaiChenNJ/MDTeamGPT) | 多轮 MDT | Safety Reviewer | 诊断为主 |
| **VERIFAI** | [harshtripathi272/VERIFAI](https://github.com/harshtripathi272/VERIFAI) | 3 轮 DS 融合 | system_uncertainty | 影像 CXR |
| **MedAgents-2** | [gersteinlab/MedAgents-2](https://github.com/gersteinlab/MedAgents-2) | Moderator 辩论 | Expert confidence | 医学 QA |
| **ClinicalMem** | [star-ga/clinicalmem](https://github.com/star-ga/clinicalmem) | 六模型共识 | 四层 DDI 管线 | RxNorm + 确定性表 |
| **Awesome 综述** | [yczhou001/Awesome-Medical-LLM-Agent](https://github.com/yczhou001/Awesome-Medical-LLM-Agent) | 论文索引 | — | — |

---

## 四、医学影像（Stage 5~7）

| 文献 / 项目 | 用途 |
|-------------|------|
| MONAI **VISTA3D** | 体数据分割 Backbone |
| **TotalSegmentator** (Wasserthal et al., 2023) | CT 全器官 |
| **SAM-Med3D** / **MedSAM** | 交互式分割 |
| **BraTS** Challenge | MRI 评估协议 |

---

## 五、MedSafe 定位声明

MedSafe 是基于 MIMIC-III 场景的**研究原型 / 演示系统**：

- 规则引擎提供可验证硬底线（`rule_strict`）
- 多轮辩论 + Critic + Moderator 模拟 MDT，**非临床验证 CDSS**
- 默认 Mock LLM 用于离线 Demo；真实审查需接入 API 并人工复核

---

## 六、BibTeX（常用）

```bibtex
@inproceedings{mdagents2024,
  title={MDAgents: An Adaptive Collaboration of LLMs for Medical Decision-Making},
  author={Kim, Seonghyeon and others},
  booktitle={NeurIPS},
  year={2024}
}

@article{johnson2016mimic,
  title={MIMIC-III, a freely accessible critical care database},
  author={Johnson, Alistair EW and others},
  journal={Scientific data},
  year={2016}
}

@article{medcoact2025,
  title={MedCoAct: Confidence-Aware Multi-Agent Collaboration for Complete Clinical Decision},
  author={Zheng, Hongjie and others},
  journal={arXiv preprint arXiv:2510.10461},
  year={2025}
}
```
