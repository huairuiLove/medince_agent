# MedSafe Stage 9 升级方案 v2：从研究原型到医院级全内科用药安全系统

## 〇、现状深度诊断

### 0.1 当前知识库完整清单

**已编码的临床安全知识（硬编码规则 + 知识图谱）：**

| 维度 | 数量 | 覆盖范围 | 评估 |
|------|------|----------|------|
| 手写 DDI 规则 | 5 条 | warfarin×3, aspirin×1, clarithromycin+simvastatin×1 | 极窄——仅抗凝/NSAIDs/他汀轴 |
| DDI-BERT 挖掘规则 | 370 条（15 high + 355 medium） | 74 种药物，4185 药对评分 | 覆盖广但无临床机制描述，全部是"咨询药师" |
| 重复成分规则 | 449 条 | 每种药物一条自动生成 | 覆盖充分 |
| Population 规则 | **3 条** | lisinopril 妊娠、losartan 妊娠、aspirin 儿童 | **极度不足** |
| Allergy 规则 | **2 条** | 青霉素交叉、NSAIDs 过敏 | **极度不足** |
| KG 药物节点 | 29 种 | 常见抗生素/心血管/NSAIDs/精神科 | 覆盖面窄 |
| KG DDI 边 | 25 条 | warfarin 为 hub（10 条），其余分散 | warfarin 中心偏重 |
| KG 食物交互 | 12 条 | 葡萄柚×3、酒精×4、绿叶蔬菜、乳制品、咖啡因 | 仅覆盖 29 种 KG 药物 |
| KG 禁忌边 | 13 条 | 妊娠×6、消化性溃疡×2、哮喘×1、肾衰×2、痛风×1 | 有框架但极不完整 |
| KG 适应症边 | 6 条 | 高血压×3、糖尿病×1、高脂血症×1、房颤×1 | 覆盖 4 个病种 |
| KG 酶代谢边 | 8 条 | CYP3A4×4、CYP2C9×2、CYP2D6×1、CYP2C19×2 | 仅 7 种药物有酶信息 |
| 药物 INN 映射 | 456 条中英文 | 涵盖 15 个药物大类 | 命名层覆盖好 |
| 院内药典 | 449 种药/1116 品规 | 含 53 种高危药品、15 种麻精药品、176 种抗菌药物分级 | 药典结构完善 |

### 0.2 关键临床安全空白（按严重程度排序）

**致命级空白（可能导致严重不良事件但系统不会报警）：**

1. **心衰多药联合**：地高辛+呋塞米（低钾→地高辛中毒）、地高辛+胺碘酮（地高辛浓度翻倍）、ACEI+螺内酯（高钾血症）、ACEI+ARB 双重阻断（肾衰+高钾）、β阻滞剂+维拉帕米/地尔硫卓（严重心动过缓/传导阻滞）
2. **QT 间期延长**：氟喹诺酮+大环内酯、SSRI+抗精神病药、胺碘酮+索他洛尔、昂丹司琼+氟哌啶醇——院内常见但系统完全不知道
3. **5-羟色胺综合征**：SSRI+曲马多、SSRI+曲坦类、SSRI+利奈唑胺、SSRI+MAO 抑制剂——仅覆盖了 fluoxetine+圣约翰草
4. **DOAC 相关出血**：利伐沙班/阿哌沙班/达比加群+NSAIDs、DOAC+SSRI（出血风险）——DOAC 在药典和 INN 映射中都有，但零规则零 KG 边
5. **阿片类+苯二氮卓**：吗啡/芬太尼+地西泮→呼吸抑制（FDA Black Box Warning）——两种药都在 KG 中但没有交互边
6. **甲氨蝶呤+NSAIDs**：NSAIDs 减少 MTX 肾清除→MTX 毒性——MTX 在药典中但无规则
7. **锂盐**：锂+NSAIDs（锂中毒）、锂+ACEI（锂中毒）、锂+利尿剂（锂中毒）——锂盐完全不在系统中

**严重级空白（影响用药合理性但系统不会提示）：**

8. **肾剂量调整**：仅 metformin 有肾衰禁忌边，无 eGFR 分级剂量指导（氨基糖苷类、万古霉素、DOACs、加巴喷丁等）
9. **肝损伤用药**：无他汀在严重肝病的禁忌、无苯二氮卓在肝性脑病的警告、无对乙酰氨基酚在肝病的剂量上限
10. **老年 Beers 准则**：population 节点存在但零规则引用——苯二氮卓跌倒风险、抗胆碱能负荷、长效磺脲类、第一代抗组胺药
11. **哺乳期用药**：population 节点存在但零规则——甲氨蝶呤、锂盐、胺碘酮禁忌
12. **癫痫药物交互**：丙戊酸+苯妥英（蛋白结合置换）、卡马西平+CYP3A4 抑制剂（卡马西平中毒）、苯巴比妥为强诱导剂——这些药在药典中但无规则
13. **糖尿病多药联合**：无磺脲类+磺脲类重复、无胰岛素+磺脲类低血糖叠加、无 SGLT2+利尿剂脱水风险
14. **华法林以外的抗凝出血**：肝素+NSAIDs、肝素+SSRI（出血风险）、氯吡格雷+PPI（仅 omeprazole 有 KG 边但无规则）

### 0.3 科室覆盖评估

当前 22 个科室已在 `departments/catalog.json` 中定义，但**真正有规则支撑的科室**仅 2 个：

| 科室 | 可用规则 | 可用 KG 边 | 评估 |
|------|----------|-----------|------|
| 呼吸科 | warfarin+抗生素 DDI、左氧+乳制品食物交互 | azithromycin/levofloxacin 节点 | ⚠️ 可用但不完整（缺茶碱、ICS 交互） |
| 神经内科 | fluoxetine+diazepam DDI | 部分精神科药物节点 | ⚠️ 可用（缺抗癫痫药、帕金森药） |
| 心内科 | warfarin DDI×10、ACEI 妊娠禁忌 | captopril/losartan/nifedipine 节点 | ❌ 缺心衰/ACS/抗心律失常核心规则 |
| 内分泌科 | metformin 肾衰禁忌、levothyroxine DDI | metformin/glibenclamide/insulin 节点 | ❌ 缺糖尿病多药联合规则 |
| 消化内科 | omeprazole DDI×4 | omeprazole 节点 | ❌ 缺 IBD/肝病用药规则 |
| 肾内科 | metformin 肾衰禁忌 | 无肾脏特异性节点 | ❌ 几乎空白 |
| 血液科 | warfarin DDI、heparin DDI | warfarin/clopidogrel 节点 | ❌ 缺化疗/免疫抑制交互 |
| 风湿免疫科 | 无 | 无 | ❌ 完全空白（MTX/来氟米特/生物制剂） |
| 感染科 | amoxicillin/levofloxacin 过敏/食物交互 | 抗生素节点×4 | ❌ 缺抗结核/抗真菌/HIV 药物交互 |
| 老年科 | aspirin 儿童规则（不适用） | 无老年特异性节点 | ❌ 完全空白（Beers 准则） |
| 妇产科 | ACEI 妊娠×2 | 妊娠 population 节点 | ❌ 缺产科/妇科完整规则 |
| 精神科 | fluoxetine+diazepam、fluoxetine+圣约翰草 | fluoxetine/diazepam 节点 | ❌ 缺锂盐/抗精神病/MAOI 规则 |
| ICU/急诊 | 无 | 无 | ❌ 完全空白（血管活性药/镇静/解毒剂） |

**结论：22 个科室中，2 个部分可用，20 个基本空白。**

---

## 一、方向一：知识库大幅扩充

### 1.1 DrugBank 数据接入

**数据源规格：**

- **下载地址**：https://go.drugbank.com/releases/latest （需注册学术账号，免费）
- **完整 XML 数据库**：`full database.xml.zip`（~120MB 压缩），包含 14,200+ 种药物
- **DDI CSV**：`drugbank-ddi.csv`（~48,584 条交互对）
- **Open Data CSV**（免注册）：`drugbank-links.csv`（基本信息）、`drugbank-enzyme-links.csv`（酶代谢）

**DDI CSV 列结构：**

| 列名 | 说明 | 映射到 MedSafe |
|------|------|---------------|
| Drug1_ID | DrugBank ID（DB00001） | drugbank_id |
| Drug1_Name | generic name | 通过 INN map 匹配 |
| Drug2_ID | DrugBank ID | drugbank_id |
| Drug2_Name | generic name | 通过 INN map 匹配 |
| Interaction_Type | 12 种类型之一 | 转换为 risk_level |
| Description | 交互机制描述 | → mechanism + summary |

**DDI severity 映射：** DrugBank 的 12 种 interaction type 映射到 MedSafe 三级：
- `major` → `high`（严重/危及生命）
- `moderate` → `medium`（需要监测/调整）
- `minor` → `low`（通常不需干预）

**实施步骤：**

1. 编写 `scripts/import_drugbank.py`：
   - 解析 DDI CSV，过滤到 INN map 可匹配的 456 种药物（预期匹配 200-300 种）
   - 将每条 DDI 转换为 `interaction_rules` JSON 格式
   - 提取酶代谢路径 → `METABOLIZED_BY` 边
   - 提取食物交互 → `FOOD_INTERACTION` 边
   - 提取适应症 → `INDICATED_FOR` 边
   - 提取禁忌症 → `CONTRAINDICATED_FOR` 边

2. 药物名交叉匹配策略：
   - DrugBank generic name → `drug_inn_map.json` 的英文 value
   - DrugBank synonyms → `drug_inn_map.json` 的中文 key
   - DrugBank ID → 新增 `drugbank_id` 字段到 INN map
   - 未匹配的 DrugBank 药物 → 新增到 INN map（扩充中文映射）

3. 输出文件：
   - `data/knowledge/drugbank_ddi_rules.json`（interaction_rules 格式）
   - `data/knowledge/drug_kg_v2.json`（nodes + edges 格式）
   - `data/knowledge/drugbank_inn_map_additions.json`（新增 INN 映射）

### 1.2 TWOSIDES 数据接入

**数据源规格：**

- **直接下载**：`https://tatonettilab-resources.s3.us-west-1.amazonaws.com/nsides/TWOSIDES.csv.gz`（~80MB）
- **数据规模**：868,221 条显著关联，覆盖 59,220 个药对和 1,301 种不良事件
- **特点**：基于 FDA FAERS 真实不良反应报告，使用 RxNorm CUI 和 MedDRA 编码

**TWOSIDES CSV 列结构（13 列）：**

| 列名 | 说明 |
|------|------|
| drug1_rxnorm_cui | 药物1的 RxNorm CUI |
| drug1_name | 药物1名称 |
| drug2_rxnorm_cui | 药物2的 RxNorm CUI |
| drug2_name | 药物2名称 |
| event_meddra_code | 不良事件 MedDRA 代码 |
| event_name | 不良事件名称 |
| PRR | Proportional Reporting Ratio |
| A | 两药+事件的报告数 |
| B | 两药但无事件的报告数 |
| C | 事件但非两药的报告数 |
| D | 既非两药也非事件的报告数 |
| mean_reporting_frequency | 平均报告频率 |

**过滤策略：**
- `PRR >= 2.0` 且 `A >= 3`（TWOSIDES 论文推荐的最低阈值）
- 优先保留与内科常见不良事件相关的：出血、QT 延长、肝毒性、肾毒性、低血糖、高钾血症、5-羟色胺综合征、呼吸抑制

**交叉验证逻辑：**

```
对于每个 TWOSIDES 信号 (drug_a, drug_b, event):
  如果 DrugBank 也有 (drug_a, drug_b) 的 DDI:
    → evidence_level 升级为 "A"（双源验证：机制 + 真实报告）
    → 在 mechanism 中追加 TWOSIDES 的不良事件描述
  如果 DrugBank 没有:
    → source = "twosides_signal"
    → evidence_level = "C"（仅观察性证据）
    → risk_level 降一级（major→medium, moderate→low）
```

**输出文件**：`data/knowledge/twosides_ddi_signals.json`

### 1.3 Population Rules 扩充（从 3 条到 80+ 条）

**按 Population 类型分类：**

#### 妊娠期禁忌（预期 35 条）

| 药物类别 | 具体药物 | 机制 | 风险 |
|----------|----------|------|------|
| ACEI 类 | lisinopril(已有), captopril, enalapril, perindopril, ramipril | 胎儿肾发育不全、羊水过少、颅骨发育不良 | high |
| ARB 类 | losartan(已有), valsartan, irbesartan, candesartan, telmisartan, olmesartan | 同 ACEI | high |
| 他汀类 | atorvastatin, simvastatin, rosuvastatin, pravastatin, fluvastatin | 胆固醇合成抑制影响胎儿发育 | high |
| 氟喹诺酮 | levofloxacin, moxifloxacin, ciprofloxacin | 软骨损伤（动物实验） | high |
| 华法林 | warfarin | 胎儿华法林综合征（鼻发育不全、骨骺点状钙化） | high |
| 甲氨蝶呤 | methotrexate | 致畸、流产 | high |
| 异维A酸 | isotretinoin | 严重致畸（脑积水、小耳、心脏缺陷） | high |
| 丙戊酸 | valproic acid | 神经管缺陷（1-2%） | high |
| 四环素 | doxycycline, tetracycline, minocycline | 牙齿着色、骨生长抑制 | medium |
| 锂盐 | lithium | Ebstein 畸形（心脏三尖瓣下移） | high |
| 非那雄胺 | finasteride | 男性胎儿外生殖器异常 | high |

#### 哺乳期禁忌（预期 8 条）

| 药物 | 机制 | 风险 |
|------|------|------|
| 甲氨蝶呤 | 分泌入乳汁，免疫抑制 | high |
| 锂盐 | 乳汁浓度高，婴儿中毒 | high |
| 胺碘酮 | 高碘含量，婴儿甲状腺功能异常 | high |
| 氯霉素 | 灰婴综合征 | high |
| 异维A酸 | 分泌入乳汁 | high |
| 麦角胺 | 抑制泌乳，婴儿中毒 | high |
| 环磷酰胺 | 免疫抑制 | high |
| 金制剂 | 分泌入乳汁 | medium |

#### 儿童禁忌/慎用（预期 10 条）

| 药物 | 年龄限制 | 机制 | 风险 |
|------|----------|------|------|
| 阿司匹林 | <16 岁(已有) | Reye 综合征 | high |
| 四环素类 | <8 岁 | 牙齿永久着色、骨生长抑制 | high |
| 氟喹诺酮 | <18 岁 | 关节软骨损伤 | medium |
| 氯霉素 | <2 岁（新生儿） | 灰婴综合征 | high |
| 可待因 | <12 岁 | CYP2D6 超快代谢→呼吸抑制 | high |
| 曲马多 | <12 岁 | 同可待因 | high |
| 苯巴比妥 | 新生儿 | 过度镇静 | medium |
| 丙戊酸 | <2 岁 | 致命性肝毒性风险增加 | high |
| 氯苯那敏 | <2 岁 | 过度镇静、呼吸抑制 | medium |
| 右美沙芬 | <4 岁 | 呼吸抑制风险 | medium |

#### 老年 Beers 准则（预期 25 条）

| 药物/类别 | Beers 原因 | 风险 |
|-----------|-----------|------|
| 地西泮 | 长效苯二氮卓，老年跌倒/骨折/认知损害 | high |
| 阿普唑仑 | 苯二氮卓类，老年跌倒 | medium |
| 氯硝西泮 | 苯二氮卓类 | medium |
| 劳拉西泮 | 苯二氮卓类 | medium |
| 格列本脲 | 长效磺脲类，老年严重低血糖 | high |
| 地高辛 | 治疗窗窄，老年中毒风险增加 | medium |
| 阿米替林 | 三环抗抑郁，抗胆碱能+镇静+直立低血压 | high |
| 氯苯那敏 | 第一代抗组胺，抗胆碱能 | medium |
| 苯海拉明 | 第一代抗组胺 | medium |
| 异丙嗪 | 抗胆碱能+镇静 | medium |
| 奥昔布宁 | 抗胆碱能，老年尿潴留/便秘/认知损害 | medium |
| 双嘧达莫 | 老年直立低血压 | medium |
| 呋喃妥因 | 肾功能减退时肺毒性 | medium |
| 甲氧氯普胺 | 锥体外系症状，老年迟发性运动障碍 | high |
| 吲哚美辛 | NSAID 中老年肾毒性/GI 出血风险最高 | high |
| 哌替啶 | 代谢物蓄积→癫痫、神经毒性 | high |
| 胺碘酮 | 老年甲状腺/肺/肝毒性 | medium |
| 可乐定 | 老年直立低血压、镇静 | medium |
| 多沙唑嗪 | 老年直立低血压 | medium |
| 萘普生 | NSAID GI 出血风险 | medium |

#### 肾功能不全剂量调整（预期 10 条）

| 药物 | eGFR 阈值 | 规则 | 风险 |
|------|-----------|------|------|
| 二甲双胍 | <30 | 禁用（乳酸酸中毒） | high |
| 达比加群 | <30 | 禁用（出血风险） | high |
| 利伐沙班 | <15 | 禁用 | high |
| 依诺肝素 | <30 | 减量或换普通肝素 | medium |
| 万古霉素 | <50 | 需 TDM 调量 | medium |
| 氨基糖苷类 | <60 | 需 TDM 调量，监测耳肾毒性 | high |
| 加巴喷丁 | <30 | 大幅减量 | medium |
| 普瑞巴林 | <30 | 大幅减量 | medium |
| 甲氨蝶呤 | <30 | 禁用（骨髓抑制） | high |
| 螺内酯 | <30 | 禁用（高钾血症） | high |

#### 肝功能不全（预期 8 条）

| 药物 | 规则 | 风险 |
|------|------|------|
| 他汀类（所有） | 活动性肝病/转氨酶持续升高→禁用 | high |
| 对乙酰氨基酚 | 严重肝病→日剂量上限 2g | medium |
| 苯二氮卓类 | 严重肝病→肝性脑病风险 | high |
| 华法林 | 严重肝病→INR 不可预测 | high |
| 甲氨蝶呤 | 肝病→禁用 | high |
| 胺碘酮 | 肝病→肝毒性叠加 | medium |
| 异烟肼 | 肝病→肝毒性高风险 | high |
| 吡嗪酰胺 | 肝病→禁用 | high |

**总计预期：35 + 8 + 10 + 25 + 10 + 8 = 96 条 population rules**

### 1.4 Allergy Rules 扩充（从 2 条到 25+ 条）

| 过敏族谱 | 触发过敏词 | 触发药物 | 交叉概率 | 风险 |
|----------|-----------|----------|----------|------|
| β-内酰胺 | penicillin, 青霉素 | amoxicillin, ampicillin, piperacillin | 高（同族） | high |
| β-内酰胺→头孢 | penicillin, 青霉素 | cephalexin, cefuroxime, ceftriaxone, cefepime | 低（1-3%） | medium |
| β-内酰胺→碳青霉烯 | penicillin, 青霉素 | meropenem, imipenem, ertapenem | 极低（<1%） | low |
| 头孢族内 | cephalosporin, 头孢 | 同代/跨代头孢 | 中（侧链相似性） | medium |
| NSAIDs 非选择性 | aspirin, 阿司匹林, nsaid | ibuprofen, diclofenac, naproxen, indomethacin | 高（COX-1 机制） | high |
| NSAIDs→COX-2 | aspirin, nsaid | celecoxib, etoricoxib | 低（选择性） | low |
| 磺胺抗菌 | sulfonamide, 磺胺 | sulfamethoxazole, sulfasalazine | 中 | medium |
| 磺胺→非抗菌磺胺 | sulfonamide, 磺胺 | furosemide, celecoxib, glimepiride, thiazides | 极低（争议） | low |
| 碘造影剂 | iodine, 碘, contrast | 所有碘造影剂 | 中 | high |
| 局麻药酯类 | procaine, 普鲁卡因 | tetracaine, benzocaine | 高（PABA 代谢） | medium |
| 局麻药酰胺类 | lidocaine, 利多卡因 | bupivacaine, ropivacaine | 低 | low |
| 大环内酯类 | erythromycin, 红霉素 | azithromycin, clarithromycin | 中 | medium |
| 氨基糖苷类 | gentamicin, 庆大霉素 | tobramycin, amikacin, neomycin | 中 | medium |
| 喹诺酮类 | ciprofloxacin, 环丙沙星 | levofloxacin, moxifloxacin | 中 | medium |
| 抗癫痫芳香族 | phenytoin, 苯妥英 | carbamazepine, phenobarbital, lamotrigine | 中（DRESS 交叉） | high |
| 别嘌醇 | allopurinol, 别嘌醇 | febuxostat | 低（不同靶点） | low |
| 肝素 | heparin, 肝素 | enoxaparin, dalteparin | 高（同类） | high |
| 胰岛素（动物源） | insulin (porcine/bovine) | 人胰岛素类似物 | 低 | medium |
| 对乙酰氨基酚 | acetaminophen, 对乙酰氨基酚 | propacetamol | 高（同成分） | high |

**总计预期：19 条 allergy/cross-allergy rules**

### 1.5 内科全覆盖：按科室的核心 DDI 规则补充

#### 心内科（补充 20+ 条核心规则）

| 规则 | 药物对 | 机制 | 风险 |
|------|--------|------|------|
| ddi_digoxin_furosemide | 地高辛+呋塞米 | 低钾血症→地高辛中毒 | high |
| ddi_digoxin_amiodarone | 地高辛+胺碘酮 | P-gp 抑制，地高辛浓度翻倍 | high |
| ddi_acei_spironolactone | ACEI+螺内酯 | 高钾血症 | high |
| ddi_acei_arb_dual | ACEI+ARB | 双重 RAAS 阻断，高钾+肾衰 | high |
| ddi_bb_verapamil | β阻滞剂+维拉帕米 | 严重心动过缓/传导阻滞/心衰 | high |
| ddi_bb_diltiazem | β阻滞剂+地尔硫卓 | 同上 | high |
| ddi_clopidogrel_omeprazole | 氯吡格雷+奥美拉唑 | CYP2C19 抑制→氯吡格雷失效 | high |
| ddi_warfarin_amiodarone | 华法林+胺碘酮 | CYP2C9 抑制→INR 飙升 | high |
| ddi_doacl_nsaids | DOAC(利伐沙班/阿哌沙班/达比加群)+NSAIDs | 出血风险叠加 | high |
| ddi_doacl_ssri | DOAC+SSRI | SSRI 抗血小板效应+DOAC 出血 | medium |
| ddi_statin_cyclosporine | 他汀+环孢素 | CYP3A4 抑制→横纹肌溶解 | high |
| ddi_clopidogrel_ppi_others | 氯吡格雷+兰索拉唑/泮托拉唑 | CYP2C19 弱抑制 | medium |
| ddi_amiodarone_simvastatin | 胺碘酮+辛伐他汀 | CYP3A4 抑制→横纹肌溶解 | high |
| ddi_digoxin_clarithromycin | 地高辛+克拉霉素 | P-gp 抑制+肾清除降低 | high |
| ddi_digoxin_verapamil | 地高辛+维拉帕米 | P-gp 抑制→地高辛浓度升高 | high |
| ddi_nitrate_pde5i | 硝酸酯+西地那非/他达拉非 | 致命性低血压 | high |
| ddi_ticagrelor_simvastatin | 替格瑞洛+辛伐他汀>40mg | CYP3A4 抑制→横纹肌溶解 | high |
| ddi_aspirin_ssri | 阿司匹林+SSRI | 出血风险叠加 | medium |
| ddi_heparin_ssri | 肝素+SSRI | 出血风险 | medium |
| ddi_sotalol_qt_drugs | 索他洛尔+QT 延长药物 | QT 间期延长→尖端扭转室速 | high |

#### 内分泌科（补充 12+ 条核心规则）

| 规则 | 药物对 | 机制 | 风险 |
|------|--------|------|------|
| ddi_insulin_sulfonylurea | 胰岛素+磺脲类 | 低血糖叠加 | high |
| ddi_metformin_contrast | 二甲双胍+碘造影剂 | 乳酸酸中毒 | high |
| ddi_sglt2_diuretic | SGLT2 抑制剂+利尿剂 | 脱水+低血压 | medium |
| ddi_levothyroxine_calcium | 左甲状腺素+碳酸钙 | 螯合→T4 吸收降低 | medium |
| ddi_levothyroxine_iron | 左甲状腺素+硫酸亚铁 | 同上 | medium |
| ddi_levothyroxine_ppi | 左甲状腺素+PPI | 胃酸降低→T4 吸收减少 | medium |
| ddi_glp1_delayed_absorption | GLP-1 激动剂+口服药 | 胃排空延迟→口服药吸收受影响 | medium |
| ddi_metformin_alcohol | 二甲双胍+酒精（已有 KG 边） | 乳酸酸中毒 | high |
| ddi_sulfonylurea_alcohol | 磺脲类+酒精 | 双硫仑样反应+低血糖 | medium |
| ddi_acarbose_digestive_enzymes | 阿卡波糖+消化酶 | 阿卡波糖疗效降低 | low |
| ddi_dpp4_acei | DPP-4 抑制剂+ACEI | 血管性水肿风险增加 | medium |
| ddi_pioglitazone_insulin | 吡格列酮+胰岛素 | 水肿+心衰风险 | medium |

#### 神经内科（补充 15+ 条核心规则）

| 规则 | 药物对 | 机制 | 风险 |
|------|--------|------|------|
| ddi_valproate_phenytoin | 丙戊酸+苯妥英 | 蛋白结合置换→游离苯妥英升高 | high |
| ddi_carbamazepine_cyp3a4i | 卡马西平+CYP3A4 抑制剂 | 卡马西平中毒（共济失调、复视） | high |
| ddi_phenobarbital_inducer | 苯巴比妥+CYP 底物 | 强 CYP 诱导→多种药物失效 | high |
| ddi_ssri_tramadol | SSRI+曲马多 | 5-羟色胺综合征 | high |
| ddi_ssri_triptan | SSRI+曲坦类 | 5-羟色胺综合征 | high |
| ddi_ssri_linezolid | SSRI+利奈唑胺 | MAO 抑制→5-羟色胺综合征 | high |
| ddi_ssri_maoi | SSRI+MAO 抑制剂 | 致命性 5-羟色胺综合征 | high |
| ddi_morphine_benzo | 吗啡/阿片类+苯二氮卓 | 呼吸抑制（FDA Black Box） | high |
| ddi_fentanyl_benzo | 芬太尼+苯二氮卓 | 呼吸抑制 | high |
| ddi_gabapentin_opioid | 加巴喷丁/普瑞巴林+阿片类 | 呼吸抑制叠加 | high |
| ddi_levothyroxine_phenytoin | 左甲状腺素+苯妥英 | 苯妥英加速 T4 代谢 | medium |
| ddi_valproate_lamotrigine | 丙戊酸+拉莫三嗪 | 丙戊酸抑制拉莫三嗪代谢→SJS 风险 | high |
| ddi_carbamazepine_valproate | 卡马西平+丙戊酸 | 卡马西平诱导→丙戊酸浓度降低 | medium |
| ddi_antiepileptic_ocp | 酶诱导抗癫痫药+口服避孕药 | CYP 诱导→避孕失败 | high |
| ddi_lithium_nsaids | 锂盐+NSAIDs | 锂中毒（肾清除降低） | high |

#### 消化内科（补充 8+ 条核心规则）

| 规则 | 药物对 | 机制 | 风险 |
|------|--------|------|------|
| ddi_omeprazole_methotrexate | 奥美拉唑+甲氨蝶呤 | PPI 减少 MTX 清除 | high |
| ddi_ppi_clopidogrel | PPI+氯吡格雷（omeprazole 强，pantoprazole 弱） | CYP2C19 竞争 | high/medium |
| ddi_methotrexate_nsaids | 甲氨蝶呤+NSAIDs | NSAIDs 减少 MTX 肾清除→毒性 | high |
| ddi_sucralfate_quinolone | 硫糖铝+喹诺酮 | 螯合→喹诺酮吸收降低 | medium |
| ddi_metoclopramide_anticholinergic | 甲氧氯普胺+抗胆碱能药 | 药理拮抗 | medium |
| ddi_ursodeoxycholic_acid_antacid | 熊去氧胆酸+抗酸剂 | 螯合→UDCA 吸收降低 | low |
| ddi_ibrutinib_ppi | 依鲁替尼+PPI | 胃酸降低→吸收减少 | medium |
| ddi_mycophenolate_ppi | 吗替麦考酚酯+PPI | 吸收降低 | medium |

#### 肾内科（补充 8+ 条核心规则）

| 规则 | 药物对 | 机制 | 风险 |
|------|--------|------|------|
| ddi_acei_potassium | ACEI+钾补充剂 | 高钾血症 | high |
| ddi_acei_tmp_smx | ACEI+复方磺胺甲噁唑 | TMP 保钾→高钾血症 | high |
| ddi_arb_potassium | ARB+钾补充剂 | 高钾血症 | high |
| ddi_nsaids_acei_renal | NSAIDs+ACEI/ARB（三联打击） | 急性肾损伤 | high |
| ddi_aminoglycoside_vancomycin | 氨基糖苷类+万古霉素 | 肾毒性叠加 | high |
| ddi_cyclosporine_nsaids | 环孢素+NSAIDs | 肾毒性叠加 | high |
| ddi_furosemide_aminoglycoside | 呋塞米+氨基糖苷类 | 耳毒性叠加 | high |
| ddi_sevelamer_oral_drugs | 司维拉姆+口服药物 | 磷酸盐结合剂吸附其他药物 | medium |

#### 血液科（补充 8+ 条核心规则）

| 规则 | 药物对 | 机制 | 风险 |
|------|--------|------|------|
| ddi_warfarin_fluconazole | 华法林+氟康唑 | CYP2C9 抑制→INR 飙升 | high |
| ddi_warfarin_metronidazole | 华法林+甲硝唑 | CYP2C9 抑制 | high |
| ddi_clopidogrel_anticoagulant | 氯吡格雷+抗凝剂 | 出血风险叠加 | high |
| ddi_methotrexate_tmp_smx | 甲氨蝶呤+复方磺胺甲噁唑 | 叶酸拮抗叠加→骨髓抑制 | high |
| ddi_methotrexate_ppi | 甲氨蝶呤+PPI | H+/K+ ATPase 抑制→MTX 清除延迟 | high |
| ddi_ibrutinib_warfarin | 依鲁替尼+华法林 | 出血风险 | high |
| ddi_lenalidomide_erythropoietin | 来那度胺+促红细胞生成素 | 血栓风险叠加 | high |
| ddi_doxorubicin_verapamil | 多柔比星+维拉帕米 | P-gp 抑制→多柔比星毒性 | high |

#### 风湿免疫科（补充 8+ 条核心规则）

| 规则 | 药物对 | 机制 | 风险 |
|------|--------|------|------|
| ddi_methotrexate_nsaids | 甲氨蝶呤+NSAIDs | MTX 清除降低→骨髓抑制 | high |
| ddi_methotrexate_leflunomide | 甲氨蝶呤+来氟米特 | 肝毒性叠加 | high |
| ddi_azathioprine_allopurinol | 硫唑嘌呤+别嘌醇 | XO 抑制→AZA 毒性致命 | high |
| ddi_cyclosporine_methotrexate | 环孢素+甲氨蝶呤 | 免疫抑制叠加+肾毒性 | high |
| ddi_hcq_retinal_toxicity | 羟氯喹+他莫昔芬 | 视网膜毒性叠加 | medium |
| ddi_tnf_live_vaccine | TNF 抑制剂+活疫苗 | 免疫抑制→疫苗感染 | high |
| ddi_cyclophosphamide_allopurinol | 环磷酰胺+别嘌醇 | 骨髓抑制增加 | medium |
| ddi_colchicine_cyp3a4i | 秋水仙碱+CYP3A4 抑制剂 | 秋水仙碱中毒（致命） | high |

#### 感染科（补充 10+ 条核心规则）

| 规则 | 药物对 | 机制 | 风险 |
|------|--------|------|------|
| ddi_rifampin_oral_contraceptives | 利福平+口服避孕药 | 强 CYP 诱导→避孕失败 | high |
| ddi_rifampin_warfarin | 利福平+华法林 | CYP 诱导→INR 暴跌 | high |
| ddi_clarithromycin_colchicine | 克拉霉素+秋水仙碱 | CYP3A4+P-gp 抑制→秋水仙碱中毒 | high |
| ddi_linezolid_ssri | 利奈唑胺+SSRI | MAO 抑制→5-羟色胺综合征 | high |
| ddi_voriconazole_statins | 伏立康唑+他汀 | CYP3A4 抑制→横纹肌溶解 | high |
| ddi_ganciclovir_myelotoxic | 更昔洛韦+骨髓抑制药 | 骨髓毒性叠加 | high |
| ddi_amphotericin_b_nephrotoxic | 两性霉素B+肾毒性药 | 肾毒性叠加 | high |
| ddi_isoniazid_phenytoin | 异烟肼+苯妥英 | CYP2C9 抑制→苯妥英中毒 | high |
| ddi_arv_ppi | HIV 蛋白酶抑制剂+PPI | 吸收降低→抗 HIV 失败 | high |
| ddi_fluconazole_qt_drugs | 氟康唑+QT 延长药物 | QT 间期延长 | high |

#### 精神科（补充 8+ 条核心规则）

| 规则 | 药物对 | 机制 | 风险 |
|------|--------|------|------|
| ddi_lithium_acei | 锂盐+ACEI | 锂中毒（肾清除降低） | high |
| ddi_lithium_diuretics | 锂盐+噻嗪类利尿剂 | 锂中毒（钠丢失→锂重吸收增加） | high |
| ddi_maoi_tyramine | MAO 抑制剂+含酪胺食物 | 高血压危象 | high |
| ddi_clozapine_cyp1a2i | 氯氮平+CYP1A2 抑制剂 | 氯氮平中毒→癫痫/粒细胞缺乏 | high |
| ddi_antipsychotic_qt | 抗精神病药+QT 延长药 | QT 延长→尖端扭转室速 | high |
| ddi_ssri_tca | SSRI+三环抗抑郁药 | CYP2D6 抑制→TCA 中毒 | high |
| ddi_carbamazepine_clozapine | 卡马西平+氯氮平 | 骨髓抑制叠加+CYP 诱导 | high |
| ddi_valproate_aspirin | 丙戊酸+阿司匹林 | 蛋白结合置换→游离丙戊酸升高 | medium |

#### 老年科（补充——复用 Beers 准则 + 多药联合规则）

老年科的核心不是独特的药物，而是**多病多药场景下的 DDI 累积**。除了 Beers 准则（已在 population rules 中覆盖），还需要：

| 规则 | 场景 | 风险 |
|------|------|------|
| anticholinergic_burden | 抗胆碱能负荷评分 ≥ 3（多个低抗胆碱能药叠加） | high |
| polypharmacy_5plus | 同时 5 种以上药物时，自动提示 DDI 筛查 | medium |
| fall_risk_combo | 苯二氮卓+阿片类+降压药+利尿剂（跌倒四联） | high |
| renal_age_adjustment | 年龄>75 且 eGFR<45 时，自动提醒所有经肾排泄药物需评估剂量 | medium |

#### ICU/急诊（补充 8+ 条核心规则）

| 规则 | 药物对 | 机制 | 风险 |
|------|--------|------|------|
| ddi_norepinephrine_maoi | 去甲肾上腺素+MAO 抑制剂 | 高血压危象 | high |
| ddi_propofol_lipid | 丙泊酚+脂肪乳 | 脂肪超载综合征 | medium |
| ddi_sedative_neuromuscular | 镇静剂+肌松药 | 呼吸抑制叠加 | high |
| ddi_vasopressor_beta_blocker | 血管加压药+β阻滞剂 | 药理拮抗 | high |
| ddi_heparin_protamine | 肝素+鱼精蛋白 | 解毒（但需注意鱼精蛋白过敏） | info |
| ddi_naloxone_opioid | 纳洛酮+阿片类 | 解毒（但可能诱发戒断） | info |
| ddi_insulin_dextrose_potassium | 胰岛素+葡萄糖+钾（GIK） | 需严密监测血糖和血钾 | medium |
| ddi_vasopressin_norepinephrine | 加压素+去甲肾上腺素 | 缺血风险叠加 | medium |

### 1.6 Drug Knowledge Graph v2 扩充目标

| 边类型 | 当前 | v2 目标 | 数据来源 |
|--------|------|---------|----------|
| Drug 节点 | 29 | 200+ | DrugBank + INN map + formulary |
| Condition 节点 | 9 | 50+ | ICD-10 映射到内科常见病种 |
| INTERACTS_WITH | 25 | 500+ | DrugBank DDI CSV + 手写核心 |
| FOOD_INTERACTION | 12 | 50+ | DrugBank food interactions |
| CONTRAINDICATED_FOR | 13 | 150+ | Population rules + DrugBank |
| INDICATED_FOR | 6 | 300+ | DrugBank + ATC 推导 |
| METABOLIZED_BY | 8 | 200+ | DrugBank enzyme data |
| BELONGS_TO_CLASS | 12 | 300+ | ATC 分类 |

**新增节点类型：**
- `Enzyme`：从 4 种扩充到 15+（增加 CYP1A2、CYP2B6、CYP2E1、UGT1A1、UGT2B7、P-gp/ABCB1、OATP1B1）
- `Transporter`：新增 P-gp、OATP1B1、OAT1/3、OCT2 等药物转运体节点
- `LabTest`：新增 INR、eGFR、血钾、血糖、QTc 等检验指标节点（用于剂量调整规则关联）

### 1.7 知识库版本管理

```
v1.0 = minimal (手写 12 条)
v2.0 = expanded_mined (375 DDI-BERT + 451 duplicate)
v3.0 = drugbank_integrated (DrugBank ~500 DDI + KG v2)
v3.1 = twosides_validated (+ TWOSIDES 交叉验证)
v3.2 = internal_medicine_full (+ 96 pop + 25 allergy + 120 科室 DDI)
v4.0 = hospital_production (全部合并 + 临床验证)
```

---

## 二、方向二：FHIR R4 标准对接

### 2.1 技术选型：使用 `fhir.resources` 库

**推荐库**：`fhir.resources`（PyPI: https://pypi.org/project/fhir.resources/）
- 当前版本 8.2.0，基于 **Pydantic V2**（与项目 Pydantic v2 一致）
- 支持 FHIR R4（通过 `fhir.resources.R4B` 子包）
- 自动校验所有 FHIR 枚举值、引用类型、必填字段
- 安装：`pip install fhir.resources`

### 2.2 架构设计：非侵入式 Adapter 层

```
HIS 系统 → FHIR R4 Bundle (collection)
              ↓ fhir.resources 解析 + 校验
         FhirAdapter.from_fhir_bundle()
              ↓ RxNorm→院内ID, LOINC→内部字段
         CpoeMedicationReviewRequest
              ↓ （零改动）
         CpoeReviewFacade.review()
              ↓ （零改动）
         CpoeMedicationReviewResponse
              ↓ alert_level→severity, category→code
         FhirAdapter.to_fhir_bundle()
              ↓ fhir.resources 序列化
         FHIR R4 Bundle (DetectedIssue[] + OperationOutcome)
              → HIS 系统
```

### 2.3 新增文件清单

```
src/fhir/
├── __init__.py
├── models.py          — 自定义 FHIR profile（MedSafeDetectedIssue 等）
├── adapter.py         — FhirAdapter 类：from_fhir_bundle() + to_fhir_bundle()
├── coding.py          — 编码系统映射（RxNorm↔院内ID, LOINC↔内部字段, SNOMED↔condition）
├── validation.py      — Bundle 完整性校验（Patient 存在、MedicationRequest 有 subject 等）
└── capability.py      — CapabilityStatement 生成（声明系统支持的 FHIR 操作）
```

### 2.4 FHIR 编码系统映射表

| 术语系统 | System URI | 用途 | MedSafe 映射 |
|----------|-----------|------|-------------|
| RxNorm | `http://www.nlm.nih.gov/research/umls/rxnorm` | 药物编码 | formulary.csv 的 rxnorm_rxcui 列 |
| ATC | `http://www.whocc.no/atc` | 药物分类 | formulary.csv 的 ATC 列 |
| SNOMED CT | `http://snomed.info/sct` | 诊断/过敏/不良事件 | 内部 condition/allergy term |
| LOINC | `http://loinc.org` | 检验指标 | 见下表 |
| ICD-10-CM | `http://hl7.org/fhir/sid/icd-10-cm` | 诊断编码 | DiagnosisItem.icd9_code (需扩展到 ICD-10) |
| HL7 v3 ActCode | `http://terminology.hl7.org/CodeSystem/v3-ActCode` | DetectedIssue 类型 | 见 2.5 |
| UCUM | `http://unitsofmeasure.org` | 剂量单位 | mg, mL, mg/kg 等 |

**LOINC 常用检验编码映射：**

| LOINC Code | 检验项目 | MedSafe PatientContext 字段 |
|-----------|---------|---------------------------|
| 69405-9 | eGFR | `egfr` |
| 2160-0 | 血肌酐 | 推导 egfr |
| 6301-6 | INR | （未来扩展） |
| 2345-7 | 血糖 | （未来扩展） |
| 2823-3 | 血钾 | （未来扩展） |
| 1751-7 | 白蛋白 | （未来扩展） |
| 8339-4 | 体重 | `weight_kg` |

### 2.5 DetectedIssue 类型映射

| MedSafe AlertCategory | FHIR ActCode | Display |
|----------------------|-------------|---------|
| `drug_interaction` | `DRUGDRUGINT` | Drug-Drug Interaction |
| `duplicate_ingredient` | `DUPTHPY` | Duplicate Therapy |
| `allergy` | `ALLERGY` | Allergy |
| `special_population` | `TREATISSUE` | Treatment Issue |
| `formulary` | `TREATISSUE` | Treatment Issue |
| `inventory` | `TREATISSUE` | Treatment Issue |
| `high_alert` | `TREATISSUE` | Treatment Issue |
| `terminology` | `TREATISSUE` | Treatment Issue |

### 2.6 新增 API 端点

```
POST /api/v1/fhir/medication-review
  Content-Type: application/fhir+json
  Accept: application/fhir+json
  内部: validate → from_fhir_bundle → review → to_fhir_bundle

GET /api/v1/fhir/metadata
  → CapabilityStatement（声明系统能力）

GET /api/v1/fhir/ValueSet/interaction-types
  → 系统支持的 DDI 类型值集
```

**对现有代码的影响：零修改。** CpoeReviewFacade、ReviewEngine、所有 Agent、辩论引擎全部不变。

### 2.7 国内标准兼容（可选）

- `src/fhir/nhic_adapter.py`：国家卫生信息标准（WS/T 500）→ FHIR 映射
- 国家医保编码 → RxNorm/ATC 桥接（通过 drug_inn_map.json 中文名）

---

## 三、方向三：药师工作台 + Override 审计链

### 3.1 后端 `src/pharmacy/` 模块

```
src/pharmacy/
├── __init__.py
├── models.py          — PharmacistReview, AlertDecision, OverrideAuditLog
├── db.py              — SQLite schema（pharmacist_reviews, alert_decisions, override_audit_logs）
├── review_store.py    — CRUD 操作
├── queue.py           — 待审查队列（按 alert_level + 时间排序）
├── override_audit.py  — 审计日志查询、统计、CSV 导出
└── stats.py           — 工作量统计（审查量、override 率、top 药物）
```

**数据模型：**

```
PharmacistReview:
  review_id: UUID
  encounter_id: str
  patient_id: str
  pharmacist_id: str (user_id)
  department: str
  created_at: datetime
  reviewed_at: datetime | None
  status: pending | reviewed | expired
  cpoe_response: CpoeMedicationReviewResponse (JSON snapshot)
  alert_decisions: list[AlertDecision]

AlertDecision:
  alert_id: str → CpoeReviewAlert.alert_id
  action: acknowledge | override | escalate | hold
  override_reason: str | None (override 时必填)
  override_risk_acceptance: low | medium | high | None
  pharmacist_notes: str | None
  decided_at: datetime

OverrideAuditLog:
  log_id: UUID
  review_id: UUID → PharmacistReview
  alert_id: str
  order_id: str
  drug_name: str
  alert_level: info | warning | hard_stop
  alert_summary: str
  pharmacist_id: str
  pharmacist_name: str
  department: str
  action: str
  override_reason: str
  risk_acceptance: str
  timestamp: datetime
  patient_outcome: str | None (事后追踪)
  supervisor_reviewed: bool
  supervisor_id: str | None
```

### 3.2 新增 API 端点

```
GET  /api/v1/pharmacy/queue          → 待审查队列（分页、按严重度排序）
GET  /api/v1/pharmacy/review/{id}    → 审查详情（含 CPOE response 快照）
POST /api/v1/pharmacy/review/{id}/decide → 提交单条 alert 决策
POST /api/v1/pharmacy/review/{id}/submit → 提交所有决策（批量）
GET  /api/v1/pharmacy/audit           → 审计日志查询（日期、药师、药物、风险筛选）
GET  /api/v1/pharmacy/audit/export    → 审计日志 CSV 导出
GET  /api/v1/pharmacy/stats           → 统计概览
```

### 3.3 CPOE 自动触发

在 `app.py` 的 `cpoe_medication_review()` 中，return 前增加：
```python
if response.requires_pharmacist_review:
    PHARMACY_QUEUE.enqueue(
        encounter_id=request.encounter_id,
        patient_id=request.patient.patient_id,
        cpoe_response=response,
        department=getattr(current_user, "dept_id", "unknown")
    )
```

### 3.4 Auth 扩展

- `src/auth/models.py`：新增 `"pharmacist"` 角色（与 `"doctor"`, `"admin"` 并列）
- `src/auth/db.py`：新增 `pharmacist_review_stats` 表
- `data/departments/catalog.json`：`pharmacy` 部门的 `nav_routes` 增加 `"/pharmacy"`, `"/pharmacy/audit"`
- 新增种子用户：`chief_pharm`（主管药师，admin 权限）

### 3.5 前端三视图

**路由：**
- `/pharmacy` → `PharmacyWorkbenchView.vue`（三栏工作台）
- `/pharmacy/review/:id` → `PharmacyReviewDetailView.vue`（审查详情）
- `/pharmacy/audit` → `OverrideAuditView.vue`（审计日志）

**PharmacyWorkbenchView 三栏布局：**
- 左栏(280px)：审查队列列表，按 alert_level 分组（hard_stop/warning/info），显示等待时间
- 中栏(flex-1)：当前审查的患者信息 + alert 列表 + 逐条决策操作
- 右栏(300px)：患者上下文（诊断、过敏、检验值、当前用药）

**Override 交互：**
1. 药师点击 "Override" → 弹出对话框
2. 必填 Override Reason（下拉+自定义）："临床获益大于风险" / "已调整剂量" / "患者知情同意" / "无替代方案"
3. 必填 Risk Acceptance（low/medium/high）
4. 若 hard_stop + rule_strict → 二次确认弹窗："此为强制拦截，Override 将记录审计日志并由上级药师复核"
5. 提交 → POST `/api/v1/pharmacy/review/{id}/decide`

**OverrideAuditView：**
- 顶部：日期范围、药师筛选、药物筛选、风险等级、导出 CSV
- 主体：审计记录表格（时间、药师、药物、Alert 类型、原因、风险接受度）
- 底部：统计条（本周 override 率、高风险 override 率、top 5 override 药物）

---

## 四、方向四：Benchmark 验证

### 4.1 按科室扩充 Benchmark Cases（100+ 个）

| 科室 | Case 数 | 核心场景 |
|------|---------|----------|
| 心内科 | 15 | 房颤抗凝桥接(3)、ACS DAPT(3)、心衰多药(4)、心律失常(3)、高血压联合(2) |
| 呼吸科 | 10 | COPD 急性加重(3)、社区获得性肺炎(2)、哮喘(2)、肺栓塞抗凝(2)、TB(1) |
| 神经内科 | 12 | 癫痫多药(3)、帕金森(2)、脑卒中二级预防(3)、偏头痛(2)、重症肌无力(2) |
| 内分泌科 | 10 | T2DM 多药(3)、甲亢(2)、甲减+DDI(2)、肾上腺(1)、骨质疏松(2) |
| 消化内科 | 8 | IBD(2)、肝硬化(2)、消化性溃疡(2)、GERD+抗血小板(2) |
| 肾内科 | 8 | CKD 剂量调整(3)、透析(2)、肾移植免疫抑制(2)、急性肾损伤(1) |
| 血液科 | 8 | 抗凝桥接(2)、化疗+DDI(2)、骨髓抑制(2)、输血相关(2) |
| 风湿免疫科 | 8 | RA 多药(2)、SLE(2)、痛风(2)、血管炎(2) |
| 感染科 | 8 | 脓毒症(2)、HIV+DDI(2)、结核+DDI(2)、真菌感染(2) |
| 精神科 | 6 | 抑郁症多药(2)、精神分裂(2)、双相(2) |
| 老年科 | 6 | Beers 准则(2)、多病多药 5+种(2)、跌倒风险(2) |
| ICU/急诊 | 6 | 脓毒症休克(2)、急性中毒(2)、多器官衰竭(2) |
| 妇产科 | 5 | 妊娠高血压(2)、妊娠感染(2)、产后出血(1) |
| **总计** | **110** | |

### 4.2 Benchmark Case JSON Schema

```json
{
  "case_id": "bench_cardio_afib_bridge_01",
  "department": "cardiology",
  "description": "68岁男性房颤患者，华法林→利伐沙班转换桥接",
  "difficulty": "hard",
  "tags": ["anticoagulation", "bridging", "elderly"],
  "request": {
    "patient_context": {
      "subject_id": 10001,
      "gender": "M",
      "age": 68,
      "diagnoses": [{"icd9_code": "427.31", "name": "Atrial fibrillation"}],
      "current_medications": [
        {"name": "warfarin", "dose": "5mg", "route": "PO", "frequency": "qd"},
        {"name": "metoprolol", "dose": "50mg", "route": "PO", "frequency": "bid"}
      ],
      "allergies": [],
      "pregnancy_status": "not_applicable",
      "egfr": 52,
      "missing_fields": []
    },
    "candidate_drugs": [
      {"name": "rivaroxaban", "dose": "20mg", "route": "PO", "frequency": "qd"},
      {"name": "enoxaparin", "dose": "40mg", "route": "SC", "frequency": "qd"}
    ]
  },
  "ground_truth": {
    "risk_level": "high",
    "block_decision": true,
    "required_alerts": [
      {"rule_id": "ddi_doacl_anticoagulant_bleeding", "category": "drug_interaction", "risk_level": "high", "must_fire": true},
      {"rule_id": "pop_elderly_doacl_renal", "category": "special_population", "risk_level": "medium", "must_fire": true}
    ],
    "should_not_fire": ["dup_rivaroxaban"],
    "expected_overridable": false
  }
}
```

### 4.3 评估脚本 `scripts/run_benchmark.py`

**评估指标：**

| 指标 | 公式 | 目标值 |
|------|------|--------|
| Alert Sensitivity | TP / (TP + FN) | ≥ 0.90 |
| Alert Specificity | TN / (TN + FP) | ≥ 0.95 |
| Risk Level Accuracy | 完全匹配 / 总数 | ≥ 0.85 |
| Block Decision F1 | 2*P*R / (P+R) | ≥ 0.85 |
| Alert Attribution | 正确关联到 order_id | ≥ 0.80 |

**运行模式：**
```bash
# 规则引擎单独（无需 LLM）
python scripts/run_benchmark.py --mode rule-only --dept all

# 完整流水线（需 LLM key）
python scripts/run_benchmark.py --mode full-pipeline --dept cardiology

# CPOE 审查
python scripts/run_benchmark.py --mode cpoe --dept all

# 知识库版本对比
python scripts/run_benchmark.py --mode compare --kb-v1 expanded_mined_v1 --kb-v2 internal_medicine_full
```

### 4.4 知识库版本对比报告

对比 v2.0（当前）vs v3.2（扩充后）在每个科室的 Sensitivity 变化，量化知识库扩充的临床价值。

---

## 五、实施路线图

```
Phase 1: 知识库扩充（2 周） ← 最关键的基础
├── Week 1a: DrugBank 导入脚本 + KG v2 骨架
├── Week 1b: TWOSIDES 导入 + 交叉验证
├── Week 1c: Population rules 96 条 + Allergy rules 25 条
└── Week 2: 科室 DDI 规则 120 条 + KB 合并 → v4.0

Phase 2: FHIR R4 对接（1 周） ← 与 Phase 1 并行
├── fhir.resources 集成 + models.py
├── FhirAdapter 双向转换
├── FHIR API 端点
└── CapabilityStatement

Phase 3: 药师工作台（1.5 周） ← 依赖 Phase 1
├── 后端 pharmacy 模块
├── Auth 扩展 + CPOE 自动触发
├── 前端 PharmacyWorkbenchView
└── 前端 OverrideAuditView

Phase 4: Benchmark 验证（1 周） ← 依赖 Phase 1
├── 编写 110 个 benchmark cases（13 个科室）
├── run_benchmark.py 评估脚本
├── 知识库版本对比报告
└── 生成验证报告文档
```

**总预估：5-6 周（Phase 1+2 并行可压缩到 4 周）**

---

## 六、对现有代码的影响汇总

| 现有文件 | 影响 | 说明 |
|----------|------|------|
| `src/knowledge_base.py` | **零改动** | JSON schema 不变 |
| `src/review_engine.py` | **零改动** | 5 个 evidence collector 不变 |
| `src/orchestrator.py` | **零改动** | Agent 选择不变 |
| `src/debate/*.py` | **零改动** | 辩论引擎不变 |
| `src/agents/*.py` | **零改动** | Agent prompt 不变 |
| `src/drug_catalog/review_facade.py` | **零改动** | CPOE 审查不变 |
| `src/drug_catalog/terminology.py` | **零改动** | 不变 |
| `src/schemas.py` | **零改动** | FHIR 模型独立在 fhir/ |
| `src/app.py` | **小改动** | +3 FHIR +7 pharmacy 端点 + CPOE 触发 |
| `src/knowledge_mining/kb_merger.py` | **小改动** | +多源合并方法 |
| `src/auth/models.py` | **小改动** | +pharmacist 角色 |
| `config.yaml` | **小改动** | 更新 KB 路径 + fhir/pharmacy 配置 |
| `data/knowledge/*.json` | **新增** | v4.0 知识库文件 |
| `frontend/src/router/index.ts` | **小改动** | +3 路由 |
| `frontend/src/api/medsafe.ts` | **小改动** | +pharmacy API |
| `frontend/src/types/index.ts` | **小改动** | +pharmacy 类型 |

**核心原则：所有升级都是加法操作。现有审查流水线一行不改。**
