# 002_preference_dpo.md

## 1. 目标

阶段 2 的目标是在阶段 1 的 SFT baseline 之上，进一步优化模型的“**多个候选里谁更像曲曲**”的选择能力。

本阶段重点解决 SFT 常见问题：

1. 回复平均化
2. 风格像，但结构不像
3. 语气像，但价值观容易漂
4. 单轮看着像，多轮容易失真
5. 像，但很假，像硬模仿

本阶段产出应是一个 **DPO / ORPO 后的 Persona 对齐模型**，使模型在候选回答中更稳定地偏向“更像曲曲、更不出戏、更不模板化”的答案。

---

## 2. 训练要求

### 2.1 训练目标

本阶段做 **Preference Learning**，推荐首选：

- DPO
- ORPO
- 或 pairwise preference tuning

不直接做 RL。

优化目标主要包括：

1. **style preference**：更偏向曲曲式语气
2. **structure preference**：更偏向曲曲式回答结构
3. **value preference**：更偏向曲曲的长期立场
4. **naturalness preference**：更自然，不像 cosplay
5. **anti-OOC preference**：减少出戏
6. **anti-bland preference**：减少“平、空、套”

### 2.2 输入输出要求

#### 输入
- `context`
- `chosen_reply`
- `rejected_reply`

#### 输出目标
让模型提升：
- 生成 `chosen` 这类答案的概率
- 降低 `rejected` 这类答案的概率

### 2.3 偏好信号要求

标注偏好时，不只是问“更喜欢哪个”，而是问：

1. 更像曲曲吗
2. 更像曲曲的结构吗
3. 更符合她的价值判断吗
4. 更自然吗
5. 更少出戏吗

### 2.4 训练边界

本阶段仍不追求：
- 长轨迹全局 reward
- 在线用户反馈闭环
- RL policy optimization

如果 DPO/ORPO 后已经足够稳定，可以不进入阶段 3。

---

## 3. 数据要求

### 3.1 必需数据

本阶段核心数据：

1. `data/05_annotations/preference_pairs_v1.jsonl`

辅助数据：

2. `data/05_annotations/style_labels_v1.jsonl`
3. `data/05_annotations/turn_sft_v1.jsonl`（用于生成候选和误差分析）

### 3.2 preference_pairs 要求

每条样本必须包含：

- 同一上下文 `context`
- 一个 `chosen_reply`
- 一个 `rejected_reply`
- 明确 judgment 字段

要求：
- `context` 必须以 user 结尾
- chosen / rejected 不可相同
- 候选来源要多样：
  - `human`
  - `sft_model`
  - `general_model`
  - `edited_negative`
  - `hard_negative`

### 3.3 preference 数据质量门槛

训练前必须满足：

1. schema 校验通过
2. 规则 QC 无 fail
3. chosen/rejected 文本不重复
4. `overall_reason_labels` 至少 1 个
5. 不同 topic / reply_type / 难度有覆盖
6. 负样本不能全是“很差的废话”，必须包含 hard negatives

### 3.4 hard negative 要求

本阶段必须专门补这几类 negative：

1. 太温柔
2. 太模板化
3. 太安全、太泛化
4. 价值观偏移
5. 结构顺序错
6. 表层像，但判断不像

### 3.5 style_labels 的作用

`style_labels_v1.jsonl` 不直接作为 DPO 主训练集，但要用来：

1. 统一偏好标注标准
2. 指导 hard negative 构造
3. 分析 chosen/rejected 的差异来源
4. 后续可训练 reward model

---

## 4. 如何量化评测

阶段 2 的评测重点不是 loss，而是 **pairwise preference 成功率** 与 **行为改进幅度**。

### 4.1 训练内指标

推荐记录：

- preference loss
- chosen logprob margin
- train/dev pair accuracy

这些指标只说明模型是否学会偏好，不代表一定更“像”。

### 4.2 核心评测指标

必须比较 **SFT baseline vs DPO 模型**：

1. **pairwise win rate**
   - 在 held-out preference 数据上，看模型是否更偏向 chosen

2. **style_similarity**
   - 是否更像曲曲的口吻和力度

3. **structure_similarity**
   - 是否更接近曲曲的组织方式

4. **value_alignment**
   - 是否更符合曲曲长期立场

5. **naturalness**
   - 是否自然，不像硬模仿

6. **OOC rate**
   - 是否降低出戏率

7. **blandness / templaticness**
   - 是否减少“安全、平、空、套”

### 4.3 阶段 2 最低验收门槛

进入阶段 3 前，至少满足：

1. held-out pairwise 准确率高于 SFT baseline
2. style / structure / value 三项至少两项提升
3. OOC rate 不升，最好下降
4. 模板化率不升，最好下降
5. 多轮稳定性不比 SFT 差

---

## 5. 如何确保达到训练目标

### 5.1 偏好标注必须拆维度

不要只做“winner/loser”粗标注。

必须拆维度：
- style
- structure
- value
- naturalness
- intent hit
- ooc risk
- blandness
- templaticness

否则 DPO 容易学成“戏剧化更强 = 更好”。

### 5.2 保证负样本质量

坏负样本太弱，会导致模型只学会打败垃圾答案。

必须加入：
- 表面像、实则判断偏了的 hard negatives
- 逻辑通顺、但价值观偏移的 negatives
- 安全模板型 negatives

### 5.3 防止戏剧化 cosplay

Preference 训练很容易把模型推向“更像舞台表演版曲曲”。

所以在 preference judgement 中必须显式关注：
- `naturalness_winner`
- `templaticness_higher`
- `blandness_higher`

### 5.4 保留用户问题命中度

不能为了更像而牺牲“答到点上”。

因此 `intent_hit` 必须是强约束维度。

### 5.5 人工抽检

每轮实验至少抽检：

- held-out preference：50~100 对
- 多轮样本：20~30 段
- 高压样本：20 条

重点看：
- 有没有更像
- 有没有更假
- 有没有更强的边界感
- 有没有变得过度锐利或过度做作

---

## 6. 训练实验如何设计

## 6.1 baseline 设计

至少做 3 组实验：

### Exp-1：SFT baseline 对照组
- 不做 preference tuning
- 用作全部指标基线

### Exp-2：标准 DPO
- 使用人工 preference pairs
- 看 style / value / OOC 是否改善

### Exp-3：DPO + hard negatives 增强
- 提高 edited_negative / hard_negative 比例
- 看是否更能稳住边界

## 6.2 数据配比实验

重点比较：

1. human vs synthetic preference 占比
2. hard negative 占比
3. 不同 topic / difficulty 是否均衡

## 6.3 关键对比维度

每轮实验至少比较：

1. pairwise accuracy
2. style_similarity
3. value_alignment
4. multi_turn_consistency
5. OOC rate
6. blandness / templaticness

## 6.4 实验记录模板

每个实验记录：

- 实验编号
- SFT 基座版本
- preference 数据版本
- 人工 preference 数量
- hard negative 数量
- train/dev loss
- held-out pair accuracy
- style_similarity
- structure_similarity
- value_alignment
- naturalness
- user_intent_hit
- ooc_rate
- blandness
- templaticness
- 主观错误分析

## 6.5 推荐实验顺序

### 第 1 轮
- 先做小规模高质量人工 preference DPO
- 验证是否真能优于 SFT

### 第 2 轮
- 引入 hard negatives
- 看是否降低出戏和模板化

### 第 3 轮
- 扩大 topic / difficulty 覆盖
- 看泛化是否更稳

---

## 7. 阶段 2 的交付物

阶段 2 完成时，至少交付：

1. 一版 DPO/ORPO 模型
2. 一套 preference 数据集版本
3. 一份 pairwise 评测报告
4. 一份 SFT vs DPO 对比报告
5. 一份出戏/模板化错误分析报告

---

## 8. 阶段 2 完成标准

满足以下条件，才考虑进入阶段 3：

1. DPO 模型相对 SFT 有稳定收益
2. chosen/rejected 区分能力明显增强
3. 风格像、结构像、价值观稳至少两项提升
4. 没有明显增加假模仿和戏剧化问题
5. 长对话仍然可能存在漂移，且仅靠 DPO 难以继续解决

如果阶段 2 后已经足够好，可不进入 RL。
