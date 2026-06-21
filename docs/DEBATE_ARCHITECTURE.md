# MedSafe 多轮辩论架构

> 融合 [ClinicalPilot](https://github.com/laksh-ya/ClinicalPilot) 辩论引擎与 [MDAgents](https://github.com/mitmedialab/MDAgents) Moderator 组讨论模式。  
> 参考文献：[REFERENCES.md](./REFERENCES.md)

---

## 一、设计目标

| 问题（旧版） | 方案 |
|-------------|------|
| 5 Agent 单轮并行，秒级返回 | 2~3 轮 Debate + Critic 修订 |
| 无置信度门控 | `confidence_threshold`（默认 0.75） |
| LLM 可覆盖规则 | Safety Panel + `rule_strict` 双层守门 |
| 用户感知「未认真审」 | 前端展示轮次 / 耗时 / 共识状态 |

---

## 二、流水线

```
PatientContext + candidate_drugs
  │
  ├─ Layer 0: ReviewEngine（12 条确定性规则）
  │
  ├─ Round 1: 5 Agent 并行初评
  │     └─ Critic（确定性 + LLM 对抗审查）
  │
  ├─ Round 2..N（max_rounds=3）:
  │     ├─ 若 consensus && min_confidence ≥ τ → 结束
  │     └─ 否则 Agent 带 Critic 批评修订 → 再 Critic
  │
  ├─ Safety Panel（并行规则审计，ClinicalPilot safety_panel）
  │
  ├─ Moderator 汇总（MDAgents group synthesis）
  │
  ├─ Chief 主席仲裁（rule_strict 不可覆盖 high）
  │
  └─ Coordinator Clarify / 人工复核 flag
```

---

## 三、模块对照

| MedSafe 模块 | 借鉴来源 | 职责 |
|--------------|----------|------|
| `src/debate/debate_engine.py` | ClinicalPilot `debate_engine.py` | 固定 2~3 轮，无无限循环 |
| `src/debate/critic_agent.py` | ClinicalPilot `agents/critic.py` | 分歧 / 低置信 / 规则遗漏 |
| `src/debate/safety_panel.py` | ClinicalPilot `safety_panel/` | 独立规则 DDI 审计 |
| `src/debate/moderator.py` | MDAgents `utils.py` Moderator | 各轮一致/冲突汇总 |
| `src/agents/chief_reviewer.py` | 原有 + Moderator 输入 | 最终仲裁 |

---

## 四、Critic 确定性检查（不依赖 LLM）

即使 Mock 模式，Critic 也会执行：

1. **block_split** — Agent 阻断意见不一致  
2. **risk_split** — 风险等级不一致  
3. **low_confidence_agents** — `confidence < threshold`  
4. **missed_rule_ids** — 规则 evidence 未被 Agent 引用  

任一项成立 → `consensus_reached = false` → 进入下一轮修订。

---

## 五、配置

`config.yaml`:

```yaml
debate:
  enabled: true
  max_rounds: 3
  confidence_threshold: 0.75
  flag_for_human_on_no_consensus: true
```

环境变量（双下划线）：

```env
MEDSAFE_DEBATE__ENABLED=true
MEDSAFE_DEBATE__MAX_ROUNDS=3
MEDSAFE_DEBATE__CONFIDENCE_THRESHOLD=0.75
```

关闭辩论（回退单轮）：`debate.enabled: false`

---

## 六、API 响应扩展

`MultiReviewResponse` / `MultiConsultResponse` 新增：

| 字段 | 说明 |
|------|------|
| `debate.rounds[]` | 每轮 Agent 意见 + Critic 输出 |
| `debate.final_consensus` | 是否达成共识 |
| `debate.flagged_for_human` | 最大轮次后仍无共识 |
| `debate.duration_ms` | 辩论耗时 |
| `debate.moderator_synthesis` | 主持人汇总 |
| `safety_panel.flags[]` | 规则命中列表 |

Case Log 新增阶段：`debate`, `safety_panel`, `critic_review`

---

## 七、与 ClinicalPilot / MDAgents 差异

| 能力 | ClinicalPilot | MDAgents | MedSafe |
|------|---------------|----------|---------|
| 辩论轮次 | 2~3 | 5 round × 5 turn | 2~3（可配置） |
| Agent 角色 | Clinical/Literature/Safety | 动态招募 | 固定 5 用药专家 |
| 外部药库 | RxNorm + DrugBank API | RAG | 本地 12 规则 + drug_kg |
| Moderator | Synthesizer | Majority + synthesis | ModeratorSynthesis |
| 异步 | asyncio | 同步 LLM | ThreadPoolExecutor |

**后续可选**：接入 RxNorm API、Agent Round 2 点对点互辩（MDAgents Turn 模式）、VERIFAI 式 system_uncertainty。

---

## 八、Mock vs 真实 API

| 模式 | 典型耗时 | LLM 调用估算 |
|------|----------|-------------|
| Mock | 数百 ms ~ 数 s | 0（模板 JSON） |
| 真实 API | 30~120 s | `(agents + critic) × rounds + moderator + chief` |

前端 `/consult` 展示 `duration_ms` 与轮次数，便于区分 Mock 与真实会诊。

---

## 九、测试

```bash
python scripts/run_integration_tests.py
# Stage 4b: S4-D1 ~ S4-D5 辩论专项
```

验收标准：

- `debate.rounds.length >= 2`（warfarin+ibuprofen case）
- `safety_panel.flags` 含 DDI 命中
- high 风险 case 仍 `consensus_block_decision = true`
