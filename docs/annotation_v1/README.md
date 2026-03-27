# QuQu Persona 标注 schema 与规范 v1

## 1. 目标

基于 `algo-plan.pdf` 的路线，把现有 `data/03_transcripts` 中已经清洗好的 section 数据，落成一套可直接执行的标注格式，服务于 5 类数据：

1. **对话级样本**：多轮 SFT 的整段对话
2. **回合级样本**：最核心的 `history -> target_reply`
3. **风格/结构/价值标签样本**：高质量人工标签集
4. **偏好对样本**：DPO / ORPO / pairwise preference
5. **评测 benchmark 样本**：离线 benchmark 与回归测试

推荐优先使用 **JSONL**。一行一个对象，便于增量写入、抽样复核、并行标注和训练。若需要导出 JSON，则使用同结构对象数组即可。

---

## 2. 与现有数据的关系

### 2.1 输入来源

优先使用：

- `data/03_transcripts/**/00_开场.json`
- `data/03_transcripts/**/*_连麦.json`
- `data/03_transcripts/**/*_评论.json`

这些文件已经满足 `data/03_transcripts/formal_output.schema.json`，适合继续做训练标注。

### 2.2 基本映射

- `host` → `persona`
- `guest` → `user`
- `call` section → 对话级 / 回合级主数据
- `comment` / `opening` section → 风格标签、价值观标签、benchmark 辅助数据

### 2.3 turn 的定义（非常重要）

**turn = 同一 section 内，同一说话人连续发言的一段。**

从现有 `sentences[]` 构造 turn 时：

1. 按 `sentences` 原顺序遍历。
2. 若相邻句子的 `speaker_id` 相同，且中间没有另一方说话，则合并为同一个 turn。
3. turn 的 `start/end` 取合并后最早/最晚时间戳。
4. 回合级 SFT 只保留 **persona=host 的目标回复 turn**；`history` 以此前所有 turn 为上下文。

---

## 3. 推荐落地文件

推荐在仓库中新增目录：

```text
data/05_annotations/
  conversation_v1.jsonl
  turn_sft_v1.jsonl
  style_labels_v1.jsonl
  preference_pairs_v1.jsonl
  benchmark_v1.jsonl
```

每个文件一行一个对象，对应下列 schema：

| 文件 | 用途 | schema |
|---|---|---|
| `conversation_v1.jsonl` | 多轮 SFT 整段对话 | `docs/annotation_v1/schemas/conversation_record.schema.json` |
| `turn_sft_v1.jsonl` | 回合级 SFT 主训练集 | `docs/annotation_v1/schemas/turn_sft_record.schema.json` |
| `style_labels_v1.jsonl` | 风格/结构/价值标签 | `docs/annotation_v1/schemas/style_label_record.schema.json` |
| `preference_pairs_v1.jsonl` | DPO/ORPO 偏好对 | `docs/annotation_v1/schemas/preference_pair_record.schema.json` |
| `benchmark_v1.jsonl` | 离线 benchmark | `docs/annotation_v1/schemas/benchmark_record.schema.json` |

---

## 4. 标签体系（v1）

### 4.1 topic_primary

`relationship, marriage, career, money, family, self_growth, emotion, education, social, health, other`

规则：

- **relationship**：恋爱关系、暧昧、择偶、复合、异地
- **marriage**：结婚、离婚、婚内关系、婚后财产
- **career**：工作选择、行业、跳槽、创业方向
- **money**：收入、资产、负债、投入产出、金钱交换
- **family**：原生家庭、父母、孩子、亲属关系
- **self_growth**：个人成长、自我建设、认知升级
- **emotion**：情绪困扰、焦虑、内耗、委屈
- **education**：学历、读研、出国、考试
- **social**：人际边界、圈层、社交策略
- **health**：身心健康、疾病、生育、医学检查

### 4.2 reply_type

`direct_answer, correct_then_answer, clarify_then_answer, counter_question, framework_breakdown, advice, value_judgment, example, refute_or_correct, boundary_setting, summary_then_advice, other`

优先判“这一轮最主要的功能”，不要贪多。

### 4.3 style_tone

`calm, sharp, restrained, gentle, humorous, teasing, direct, reserved`

说明：

- `sharp`：明确、带切割感、纠偏力度强
- `restrained`：不煽情、不夸张
- `direct`：短路径、低铺垫、直接下判断
- `reserved`：明确保留、不过度下结论

### 4.4 structure_pattern

`conclusion_first, define_then_answer, question_first, correct_premise_first, framework_first, example_first, compare_options_first, other`

只标 **主结构**。

### 4.5 reasoning_patterns

可多选：

`definition_clarification, causal_analysis, tradeoff_analysis, counterexample_test, boundary_setting, problem_reframing, resource_constraint_check, goal_alignment_check, other`

### 4.6 value_signals

可多选：

`long_termism, realism, user_value_first, business_closure_first, anti_false_proposition, anti_empty_talk, result_oriented, honest_reservation, other`

### 4.7 interaction_policies

6 个布尔字段，必须显式标：

- `asks_clarifying_question_first`
- `corrects_premise_first`
- `reduces_complexity_first`
- `refuses_invalid_premise`
- `comforts_emotion_explicitly`
- `reframes_problem`

注意：这里标的是**是否发生**，不是“是否应该发生”。

---

## 5. 各数据文件如何标

## 5.1 conversation_v1.jsonl

### 标注单位

一条 `call section` = 一条 conversation record。

### 必填原则

- `turns` 必须是 turn 级，不是 sentence 级。
- `turns.role` 只允许 `user/persona`。
- `topic_primary` 必填；`topic_secondary` 可多选。
- `train_split` 在入库时就定好，避免后续泄漏。

### 适用场景

- 多轮 SFT
- 多轮一致性评测
- conversation-level reward model

---

## 5.2 turn_sft_v1.jsonl

### 标注单位

一条 **persona 回复 turn** = 一条 record。

### 生成规则

- `history` 必须以用户问题或上一轮用户追问结束。
- `target_reply` 必须是 host/persona 的真实回复。
- 若连续多个 host turn 中间没有 guest 打断，可继续合并为一个目标回复。

### 必填核心标签

- `reply_type`
- `topic_primary`
- `difficulty`
- `user_emotion`
- `transcript_quality`

这份数据是主训练集，优先保证覆盖面和一致性，不要求每条都做人设高精标签。

---

## 5.3 style_labels_v1.jsonl

### 标注单位

对 `turn_sft` 的一个子集，做人设高精标签。

### 适用范围

优先标：

1. 高代表性的 host 回复
2. 容易“像/不像”拉开差距的回复
3. 高压、纠偏、反问、立场表达明显的回复
4. `comment/opening` 中高密度价值观表达的片段

### 证据要求

建议每条至少写 1~2 条 `evidence`：

- `quote`：直接摘一句关键表达
- `context_fact`：上下文事实，例如“用户前提错误，回复先纠偏”

### confidence

- `1`：勉强可判
- `2`：较确定
- `3`：高度确定

---

## 5.4 preference_pairs_v1.jsonl

### 标注单位

同一上下文下，`chosen_reply` vs `rejected_reply` 一对。

### 标注原则

不是问“更喜欢哪个”，而是问：

1. 哪个更像曲曲
2. 哪个更像她的结构和思路
3. 哪个更符合长期立场
4. 哪个更自然，不像硬 cosplay
5. 哪个更少出戏

### 允许的候选来源

- `human`
- `sft_model`
- `general_model`
- `edited_negative`
- `hard_negative`

### judgement 字段解释

- `*_winner = chosen/rejected/tie`：该维度谁更优
- `ooc_risk_higher`：谁更“出戏”
- `blandness_higher`：谁更平、更空、更像安全模板
- `templaticness_higher`：谁更像模仿秀
- `overall_reason_labels`：至少选 1 个主因

---

## 5.5 benchmark_v1.jsonl

### 标注单位

一个评测 case = 一条 record。

### 五类 benchmark

- `normal_qa`
- `multi_turn_followup`
- `adversarial`
- `cross_topic`
- `ooc_trap`

### expected 的设计原则

benchmark 不强制依赖唯一标准答案，更推荐：

- 期望回复类型
- 期望风格/结构/价值信号
- 必须避免的表达
- 最大可接受 OOC 风险

也就是说，benchmark 的核心是 **rubric**，不是“背参考答案”。

---

## 6. 标注作业流程（推荐）

### 阶段 A：自动预填

程序自动从 `formal_output` 预填：

- `source.*`
- `start/end`
- `turns/history/target_reply`
- `guest_persona`
- 初步 `topic_primary`

### 阶段 B：人工核对 turn

人工只做两件事：

1. 看 turn 是否切错
2. 看 user / persona 是否映射错

### 阶段 C：核心标签

先打 `topic / reply_type / difficulty / user_emotion`。

### 阶段 D：高精标签子集

抽样补 `style/structure/reasoning/value/interaction`。

### 阶段 E：偏好数据

从 `turn_sft` 样本生成多个候选回复，再做人类 pairwise judgement。

### 阶段 F：benchmark

从真实案例和人工构造 case 中沉淀 benchmark 集。

---

## 7. 质检规则（必须执行）

### 通用 QC

1. `record_id / sample_id / label_id / pair_id / benchmark_id` 全局唯一
2. 所有 `start <= end`
3. 文本不得为空串（除明确允许的空 comment，不建议进入训练集）
4. `history` 的最后一轮不得是 persona，除非这是 benchmark 的中间态输入
5. `chosen_reply.text != rejected_reply.text`
6. `topic_primary` 只能有一个
7. `style_tone_primary` / `structure_pattern_primary` 只能有一个

### 强约束 QC

- `conversation_v1.jsonl`：必须来自 `call section`
- `turn_sft_v1.jsonl`：`target_reply` 必须是 persona 回复
- `style_labels_v1.jsonl`：至少一项 `reasoning_patterns`，至少一项 `value_signals`
- `preference_pairs_v1.jsonl`：`overall_reason_labels` 至少 1 项
- `benchmark_v1.jsonl`：必须有 `target_reply_types` 和 `max_ooc_risk`

---

## 8. 标注边界（避免引入噪声）

1. **不脑补事实**：源文本没说，不准补。
2. **不重写原话**：训练字段里的 `text` 一律保留原始清洗文本；标注只加标签，不改写答案。
3. **不把“我觉得像”当标签**：必须落到结构、价值、互动动作。
4. **遇到模糊样本宁可降置信度，不要强判。**
5. **评论段和开场段** 主要用于风格/价值标签，不强行塞进对话级 SFT。

---

## 9. 推荐抽检比例

- `conversation_v1.jsonl`：10%
- `turn_sft_v1.jsonl`：10%~20%
- `style_labels_v1.jsonl`：100% 复核
- `preference_pairs_v1.jsonl`：100% 复核
- `benchmark_v1.jsonl`：100% 复核

---

## 10. 最小可行落地顺序（建议）

1. 先做 `turn_sft_v1.jsonl`
2. 同步沉淀 `conversation_v1.jsonl`
3. 抽样做 `style_labels_v1.jsonl`
4. 生成并标注 `preference_pairs_v1.jsonl`
5. 最后沉淀 `benchmark_v1.jsonl`

这条路径和 `algo-plan.pdf` 是一致的：**先数据重构，再 SFT，再 preference，再 benchmark**。


---

## 11. 质检脚本

已提供质检脚本：

```bash
python scripts/qc_annotation_records.py   --input-dir data/05_annotations/examples   --out-dir data/05_annotations/examples_qc
```

默认能力：

- 按 `record_type` 自动匹配 schema
- 校验 JSON/JSONL 结构是否符合 schema
- 执行规则 QC：
  - 记录 ID 唯一性
  - turn / message 索引连续性
  - role 与 speaker_id 映射一致性
  - history/context 末轮约束
  - target_reply 与 source 的时间/turn 对齐
  - preference 引用 turn_sft、turn_sft 引用 style_label 的跨文件检查

输出：

- `annotation_qc_summary.json`
- `annotation_qc_records.jsonl`
- `annotation_qc_invalid.jsonl`
