# MedSafe 后端算法架构 — 演讲讲稿

> 对应 PPT: MedSafe_Backend_Architecture_v3.pptx · 16 页 · 预计时长 28-35 分钟

---

## 第 1 页 · 封面

各位好，今天向大家汇报的是 MedSafe 智能用药安全审查系统的后端算法架构。

MedSafe 的核心使命是在医嘱录入环节，通过确定性规则引擎和多智能体协作辩论，对用药方案进行全方位安全审查。经过 10 个阶段的迭代，系统后端已经积累了超过 25,000 行代码、143 个 Python 模块，覆盖 26 个临床科室，维护着近 4 万条安全规则。

技术栈方面，后端基于 FastAPI 构建，前端使用 Vue 3，Python 版本为 3.13。在 AI 层面，我们集成了 Qwen3-VL 视觉语言模型用于影像分析，DeepSeek 用于报告合成，MONAI 框架用于医学影像分割。

---

## 第 2 页 · 系统架构总览

先看整体架构。系统是一条六阶段流水线，核心设计理念是"确定性优先"和"人在回路"。

第一阶段是确定性规则引擎，这是整个系统的安全底座。它包含近 4 万条 DDI 规则、人群禁忌、过敏交叉等硬拦截逻辑，全部在 LLM 之前执行，安全底线不可被大模型覆盖。

第二阶段是多智能体协作辩论。我们设计了 7 个以上的专科 Agent，采用 MDAgents 加 ClinicalPilot 的混合辩论范式，每个 Agent 只看自己职责范围内的证据，实现证据隔离。

第三阶段是主任仲裁引擎，采用 LLM 加确定性双轨机制。当 Agent 之间出现分歧时，由主任仲裁 Agent 进行最终裁决，但规则引擎的"高风险"判定不可被降级。

第四阶段是影像 VLM 管线，集成了 Qwen3-VL 视觉分析和 6 个分割模型，DeepSeek 负责最终的报告合成。

第五阶段是澄清补全引擎，当关键信息缺失时引导用户补全。

右侧列出了 8 条核心设计理念，特别值得强调的是"优雅降级"——当 LLM 不可用时，系统会自动切换到纯规则模式，保证基本的安全审查能力不中断。

---

## 第 3 页 · 确定性规则引擎

这一页展开讲规则引擎。它的核心是 ReviewEngine，包含 6 类证据收集器。

第一类是成对 DDI 检查，对每一个候选药物与所有在用药做双向查询，使用 pair_cache 对称去重，避免重复规则。

第二类是 DDI-BERT 机器学习预测。这里有一个重要的设计：ML 模型只对 JSON 规则未覆盖的药物对生效，是互补关系而非替代。

第三类是重复成分检测，把不同品牌名归一化到通用名，检测"换了个名字但其实是同一种药"的情况。

第四类是特殊人群检查，支持妊娠、哺乳、eGFR 肾功能、肝功能、年龄 5 种字段类型的匹配。

第五类是过敏交叉反应，通过子串匹配扫描 KB 中的过敏规则。

第六类是临床场景检测，包括多药联用超过 5 种、跌倒风险组合、老年肾功能调整、抗胆碱负荷 4 种场景。

全部 6 类证据收集在 50 毫秒内完成。规则引擎还集成了科室优先级过滤，根据科室调整证据的优先级顺序。风险升级逻辑是 none 到 low 到 medium 到 high 到 unknown，其中 high 和 unknown 都会触发硬拦截。

---

## 第 4 页 · 多源知识融合体系

规则引擎背后是四大知识来源。

第一是结构化知识库 hospital_production_v4，包含 39,679 条 DDI 规则、449 条重复成分规则、103 条特殊人群规则、21 条过敏交叉规则，以及 494 个药物别名映射。

第二是药物知识图谱 v2，772 个节点涵盖药物、靶点、通路，40,481 条边关系，支持 GraphRAG 多跳推理，集成了 ATC 分类体系。

第三是 TWOSIDES 真实世界信号数据。原始数据有 4290 万条报告，经过质量过滤保留 458 万条，最终提取出 39,280 条显著信号，筛选条件是 PRR 大于等于 2.0 且计数大于等于 3。

第四是 DDI-BERT 机器学习补充层。Bio_ClinicalBERT 模型预测未知药物对的交互风险，仅对 JSON 规则未覆盖的药物对生效，与规则引擎形成互补。

这四个来源的融合策略是：结构化规则做硬拦截，知识图谱辅助多跳推理，真实世界信号补充覆盖面，ML 模型填补规则空白。

---

## 第 5 页 · 数据集与模型来源

这一页详细列出系统依赖的 12 类数据源，分为三大类。

第一类是公开临床数据集，共 5 个。MIMIC-III 来自 MIT PhysioNet，提供 ICU 患者的电子健康记录，包括诊断、处方、检验和病程记录共 26 张表，我们从中提取了患者上下文。FAERS 和 TWOSIDES 来自 FDA 和哥伦比亚大学 Tatonetti 实验室，包含 64,000 多个药物-不良事件信号，经过 PRR 统计挖掘筛选出 39,280 条显著信号。PubChem 来自 NIH，提供药物化学结构 SMILES 字符串，通过 REST API 实时查询。WHO ATC 是世界卫生组织的药品分类系统，我们直接使用其分类体系。RxNorm 来自美国国家医学图书馆，提供标准化的药品标识符 RxCUI。

第二类是 HuggingFace 模型仓库，共 4 个。Bio_ClinicalBERT DDI 用于药物对交互概率预测，覆盖 4,185 个药品对。Med7 用于临床文本中的药品实体抽取，包括药名、剂量、频次和途径。multilingual-e5-small 用于药品目录的语义搜索文本嵌入。影像分割模型来自 MONAI 和 HuggingFace，包括 VISTA3D、SAM-Med3D、TotalSegmentator、BraTS 肿瘤和 CXR 病灶检测。

第三类是临床专家人工编写的数据，共 3 个。基于 Beers 标准、FDA 黑框警告、CYP450 药理学和临床指南编写了约 300 条 DDI 规则、50 条人群规则、20 条过敏规则和 4 条场景规则。演示处方集模拟了真实医院的 1,120 种药品目录。中文-英文药品名映射表包含约 230 条人工维护的对照数据。

---

## 第 6 页 · 专科医生多智能体架构

现在进入多智能体部分。系统有 7 个核心 Agent，每个都有明确的角色分工和证据隔离范围。

临床药师负责 DDI、重复用药和剂量审查，只看 drug_interaction 和 duplicate_ingredient 类别的证据。内科主治负责适应症和方案评估，只看 clinical_scenario 证据。过敏专员负责过敏和交叉过敏检测，只看 allergy_contraindication 和 ADR 相关证据。药房库管检查处方集和库存，直接查询 DrugCatalog。特殊人群审查专员关注妊娠、老年、肝肾功能。专科医师处理科室特定的约束。信息协调员负责生成澄清问题。

三个关键机制保证了 Agent 的专业性：

第一是角色证据过滤。每个 Agent 通过 filter_*_evidence() 函数只看自己职责范围的证据。比如临床药师看不到过敏证据，就不会越界讨论过敏问题。

第二是外来标记清洗。即使 LLM 输出中引用了角色外的证据，也会被自动剥离。比如临床药师的输出中如果出现"过敏"相关内容，会被过滤掉。

第三是 YAML 动态注册。Agent 通过 AgentSpec 定义，包括 debate 开关、skill 片段、activate_when 激活条件。科室专科 Agent 按 drug_keywords、department、age 等条件动态激活。

---

## 第 7 页 · 多智能体辩论机制

辩论机制是我们系统的一个核心创新，采用了 ClinicalPilot 加 MDAgents 的混合范式。

辩论流程分四步：

第一步，Round 1 并行审查。所有 Agent 通过 ThreadPoolExecutor 并行执行 review()，各自独立产出 AgentOpinion，包含风险等级、拦截决策、置信度和理由。

第二步，Critic 对抗审查。CriticAgent 执行确定性检查——检测 block 分歧、风险分歧、低置信度 Agent、遗漏的规则证据——然后再加上 LLM 对抗审查，产出 CriticOutput。

第三步，共识判定。共识达成的条件是：Critic 认为没有分歧，且所有 Agent 的最低置信度大于等于 0.75。如果达成共识，退出循环进入综合阶段。如果未达成，进入修正轮。

第四步，Round 2 到 N 的修正审查。Critic 的输出被格式化为修正文本，注入到每个 Agent 的重新审查中。这里有一个设计细节：Agent 在修正轮会获得 +0.08 的置信度提升，上限 0.92，模拟"考虑了批评意见后信心增强"的效果。最多进行 3 轮。

两种模式的分工：ClinicalPilot 的对抗修正负责迭代收敛，MDAgents 的 Moderator 负责辩论结束后的综合汇总，产出 integration_summary 提交给主任仲裁。

SafetyPanel 是一个独立于辩论运行的规则审计模块，它并行运行 ReviewEngine 的完整审查，当它建议拦截且 rule_strict 模式开启时，可以强制拦截。

---

## 第 8 页 · 医学影像管线上

接下来介绍影像处理管线，这是 Stage 10 的重要成果。整个模块有 24 个 Python 文件、3,085 行代码。

数据源方面，ImagingCatalog 扫描 5 个数据集：MIMIC-IV CT（重症监护影像）、MIMIC-CXR-JPG（胸部 X 光，附带放射报告 XML 解析）、BraTS 2024（脑肿瘤 MRI，包含 t1c/t1n/t2w/t2f 四种模态）、KiTS19（肾脏肿瘤 CT）和 Chest CT。

分割模型方面，我们实现了 6 个后端，通过 SegmentService 串行加载——这是出于 16GB 内存安全考虑，每次只加载一个模型，推理完成后释放 GPU 缓存。

CXR 病灶检测使用 U-Net 做肺炎类 opacity 检测，加上 Grad-CAM DenseNet121 做积液、气胸等病变定位。BraTS 肿瘤分割使用 MONAI Bundle，提取全肿瘤区、肿瘤核心区和增强肿瘤区三个区域。VISTA3D 是 MONAI 的 3D 体积分割模型，支持真实 3D 推理和从 2D JPG 生成伪 3D。TotalSegmentator 走 2D 快速模式。SAM-Med3D 使用空间注意力机制，在 CPU 上运行轻量代理。SAM2D 是点或框提示驱动的区域生长。

每个模型推理完成后，结果以 overlay PNG 和 mask NIfTI 的形式持久化到 imaging_cache 目录。

---

## 第 9 页 · 医学影像管线下

影像管线的下半部分是 VLM 分析和报告合成。

VLM 视觉分析使用 Qwen3-VL-Plus 模型，通过阿里云百炼平台的 OpenAI 兼容 API 调用。输入是最多 12 张 base64 编码的 PNG 图片加上临床文本提示，温度设为 0.1 以保证输出的确定性。VLM 输出结构化 JSON，包含临床分析、影像发现、用药建议、推荐药物、过敏信息、诊断、症状、主诉、麻醉手术信息、推理链和风险等级。分析结果缓存在 ImagingAnalysisCacheStore 中。

DeepSeek 报告合成使用 deepseek-chat 模型，角色定位是"临床多智能体会诊主席"。它接收 VLM 分析结果、Agent 意见、仲裁结果、规则引擎输出和推理链提示，温度 0.2。输出包含临床分析、影像发现、用药建议、药学评估、过敏分析、麻醉手术、风险总结和推理链。

完整的报告生成流程分 6 步：先检查 VLM 缓存，已有则直接复用；然后解析候选药物；接着调用 ReportGenerator 运行完整的多智能体辩论流水线；再用 DeepSeek 合成最终报告；然后缓存报告；最后持久化到 CaseStore，case_kind 标记为 "imaging_report"。

---

## 第 10 页 · CPOE 医嘱录入审查流水线

这一页展示的是从医嘱录入到最终签发的完整流水线。

7 个阶段依次是：医嘱录入（支持 CPOE 和 FHIR Bundle）、药物解析（hospital_drug_id 映射到 CandidateDrug）、目录预警、规则引擎、智能体辩论、主任仲裁、签发报告。

目录预警系统由 DrugCatalogService 驱动，产生 4 种预警：UNRESOLVED_DRUG 是药物 ID 无法解析；NOT_IN_FORMULARY 是药物不在处方集内，会触发拦截并提供替代方案；OUT_OF_STOCK 是库存为零，同样拦截并推荐有库存的替代品；HIGH_ALERT_DRUG 是高警示药物，需要双人核查。

严重级别映射逻辑是：risk=high 且 rule_strict 模式时为 hard_stop，医嘱不可执行；risk=high 但非严格模式时为 warning，药师可以覆盖；risk=medium 为 warning；risk=low 或 none 为 info。

分支决策逻辑的关键点是：规则引擎发现高风险直接拦截，不进入辩论；Agent 共识达到 0.75 自动签发；有分歧提交主任仲裁；信息缺失走 ClarifyEngine；药师覆盖决定会记录到 OverrideAuditLog，全程可追溯。

---

## 第 11 页 · 科室专科化引擎

系统覆盖 26 个临床科室，每个科室都有差异化的审查逻辑。

科室模块包含 4 个核心文件：formulary.py 管理科室处方集，定义首选药物、替代药物和禁忌药物；priority.py 处理科室优先级规则，比如急诊科的紧急场景覆盖；context.py 负责科室上下文注入，为 Agent 提示词提供科室特定信息；stats.py 做科室审查统计和拦截率分析。

专科 Agent 路由的链路是：请求进入后识别科室，加载科室上下文，注入 Agent 提示词，处方集过滤，专科安全约束，然后进入辩论。

DepartmentSpecialistAgent 的激活条件包括：always 标志、科室匹配、药物关键词、药物类别、年龄阈值、妊娠状态。

Skill 组合系统实现了模块化提示词工程：YAML 注册定义 AgentSpec，load_skill_body() 从 Markdown 片段加载技能内容，compose_system_prompt() 组合最终的系统提示词，支持 {{variable}} 模板替换。每个 Agent 可以叠加多个 skill 片段。

---

## 第 12 页 · FHIR R4 互操作性

FHIR R4 适配层实现了与医院 HIS/EMR 系统的标准化对接。

核心是 FhirAdapter，470 行代码，实现了 MedicationRequest 到内部处方模型的双向转换、Patient 到人群特征的提取、Bundle 的批量请求编排。

整个模块 6 个文件、1,058 行，基于 fhir.resources 8.2.0 和 Pydantic V2。

提供 4 个 API 端点：POST MedicationRequest/$review 做单条医嘱审查，返回 DetectedIssue Bundle；POST Bundle/$review 做批量审查加事务编排；GET /metadata 返回 CapabilityStatement 用于服务发现；GET /ValueSet/interaction-types 返回交互类型代码集。

数据流是：FHIR Bundle 进来，FhirAdapter 转换为内部格式，交给 CpoeReviewFacade 审查，规则引擎执行，最终结果转换回 FHIR DetectedIssue Bundle 返回。

---

## 第 13 页 · 药师工作台

药师工作台实现了"人在回路"的核心机制。

三级角色权限体系：L3 临床药师可以审核、覆盖和签发；L4 药房主管可以审批覆盖和管理库存；L5 质控审计可以全局查询和导出报表。

审计链是全程可追溯的：系统生成审查建议并按 severity 分级，药师确认或覆盖时必须填写 override_reason，覆盖原因记录到 OverrideAuditLog，质控审计角色可以追溯查询，最终生成统计报表。

模块提供 7 个 API 端点，包括待审队列、决定（accept/override/escalate）、最终签发、审计日志、CSV 导出和绩效统计。

---

## 第 14 页 · Benchmark 验证体系

系统建立了完整的 Benchmark 验证体系。

309 个测试用例覆盖 26 个科室，核心指标全部达到 100%：规则命中率、严重级别准确率、科室覆盖率、人群规则触发率、过敏交叉检出率、场景规则触发率。

左侧展示了用例数排名前 10 的科室，心内科 22 例最多，内分泌科 18 例次之。

右侧的评估维度中，特别值得一提的是知识库版本对比：早期的 expanded_mined_v1 版本敏感度只有 8.2%，经过多轮迭代升级到 hospital_production_v4 后达到了 100%。这说明了多源知识融合策略的有效性。

---

## 第 15 页 · 技术亮点与系统规模

总结系统的技术亮点和规模。

25,000 多行后端代码，143 个 Python 模块，20 多个子模块，经历 10 个迭代阶段。

左侧的模块规模图可以看到，knowledge_mining 3,192 行是最大的模块，其次是 imaging 3,085 行和 agents 2,011 行。这三个模块加上 app.py 的 1,540 行 API 层，构成了系统的四大核心。

右侧总结了 10 条设计原则：确定性优先、全链路审计、FHIR R4 互操作、人在回路、数据驱动、验证闭环、科室专业、性能保障、优雅降级、VLM 影像联动。

---

## 第 16 页 · 模块连接全景图

最后一页是模块连接全景图。

中心是 ReviewEngine 确定性规则核心，它被所有上层模块共享。左侧连接 SafetyKnowledgeBase 和 CatalogAware KB 提供知识查询，SafetyModels 提供 DDI-BERT 和 Med7 模型支持，DepartmentRulePrioritizer 提供科室优先级过滤，ImagingCatalog 和 SegmentService 提供影像数据。

右侧连接 MultiAgentOrchestrator 负责辩论到仲裁到澄清的完整流程，CpoeReviewFacade 处理 CPOE 医嘱审查，FhirAdapter 桥接 FHIR R4 标准。

底部是 PharmacyQueue 加 OverrideAuditStore 实现人在回路，CaseStore 负责全链路持久化。

底部的优雅降级策略保证了系统的鲁棒性：LLM 不可用时切换纯规则模式，DDI-BERT 未加载时仅用 JSON 规则，VLM 未配置时影像分割独立运行，药物目录未加载时使用基础 KB 查询。/health 端点实时报告所有子系统的状态。

以上就是 MedSafe 后端算法架构的完整汇报，谢谢大家。

---

> **备注**：讲稿按自然语速约 28-35 分钟。如需缩减，建议省略第 5 页（数据集来源）、第 12 页（FHIR）和第 16 页（全景图）的详细讲解，仅做快速带过。
