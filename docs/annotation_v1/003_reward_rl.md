# 003_reward_rl.md

## 1. 目标

阶段 3 是 **可选阶段**。只有在阶段 1 + 阶段 2 已经完成，但模型仍然存在明显的**长对话漂移、角色失稳、整段对话后人设崩塌**时，才进入本阶段。

本阶段目标：

1. 强化长对话中的角色稳定性
2. 让模型在 trajectory 级别更像曲曲
3. 降低多轮累计后的价值观漂移
4. 降低“第一轮像、第五轮崩”的情况

本阶段不是必须项。

---

## 2. 训练要求

### 2.1 适用前提

只有在以下情况同时满足时，才建议上 RL：

1. SFT baseline 已可用
2. DPO/ORPO 已带来明显收益
3. 主要剩余问题集中在：
   - 长对话漂移
   - 多轮角色不稳
   - 局部像、整体不像
4. 有足够评测数据或 reward 信号支撑

### 2.2 训练目标

本阶段优化的是 **trajectory-level persona consistency**。

可以拆成两类奖励：

1. **turn-level reward**
   - 当前这一轮像不像
   - 有没有出戏
   - 有没有答到点上

2. **conversation-level reward**
   - 整段对话结束后是否仍然像曲曲
   - 是否前后一致
   - 是否价值观稳定

### 2.3 reward 设计要求

reward 必须是多头，而不是单一“像不像”分数。

推荐 reward 头：

- `style_similarity`
- `structure_similarity`
- `value_alignment`
- `multi_turn_consistency`
- `user_intent_hit`
- `out_of_character_penalty`
- `blandness_penalty`
- `templatic_penalty`

### 2.4 reward 组合要求

每轮 reward 建议由：

- `immediate_reward_t`
- `final_conversation_reward`

组合而成。

即：
- 当前轮局部表现
- 整段对话全局表现

共同决定更新方向。

---

## 3. 数据要求

### 3.1 必需数据

本阶段推荐使用：

1. `conversation_v1.jsonl`
2. `turn_sft_v1.jsonl`
3. `style_labels_v1.jsonl`
4. `benchmark_v1.jsonl`

如果有线上交互，还可加入：

5. 真实用户反馈日志

### 3.2 reward model 数据要求

reward model 的训练样本，推荐输入：

- 对话历史
- 当前用户发言
- 模型回复
- 可选 persona rule card

输出多头分数：

- style_similarity
- structure_similarity
- value_alignment
- multi_turn_consistency
- user_intent_hit
- out_of_character_risk
- blandness
- templaticness
- overall

### 3.3 style_labels 的作用

`style_labels_v1.jsonl` 用于：

1. 训练细粒度 reward model
2. 给 reward 头提供监督依据
3. 校验 reward 是否真的学到“结构/价值”，而不是只学语气

### 3.4 benchmark 的作用

`benchmark_v1.jsonl` 是本阶段最重要的离线评测集，用于：

1. RL 前后对比
2. 检查 reward hacking
3. 检查是否出现“分数变高但越来越假”

### 3.5 数据质量门槛

进入 RL 前必须满足：

1. reward 训练数据 schema/QC 全通过
2. benchmark 覆盖：
   - normal_qa
   - multi_turn_followup
   - adversarial
   - cross_topic
   - ooc_trap
3. reward 标注维度完整
4. benchmark 不泄漏到训练集

---

## 4. 如何量化评测

阶段 3 的核心不是单轮 improvement，而是 **长对话整体收益**。

### 4.1 reward model 评测

先评估 reward model 本身：

1. 多头分数相关性
2. 与人工 judgement 一致性
3. 在 held-out set 上能否区分好坏回答

如果 reward model 不可靠，不应进入 policy RL。

### 4.2 policy 评测指标

RL 前后必须比较：

1. **multi_turn_consistency**
2. **value_alignment**
3. **OOC rate**
4. **templatic_rate**
5. **blandness_rate**
6. **user_intent_hit**
7. **trajectory-level overall score**

### 4.3 核心验收维度

最重要的是：

1. 长对话更稳了吗
2. 施压后立场更不容易漂了吗
3. 整体更自然了吗
4. 是否出现 reward hacking

### 4.4 阶段 3 的最低验收门槛

如果做 RL，至少要达到：

1. 多轮一致性显著优于 DPO baseline
2. OOC rate 不升
3. 模板化率不升
4. benchmark 上没有出现“像，但假”明显恶化
5. reward model 与人工判分保持基本一致

---

## 5. 如何确保达到训练目标

### 5.1 先验收 reward model，再训 policy

最常见错误是 reward model 还没验证好，就直接做 RL。

要求：
- 先单独验证 reward model
- 确认它区分“像/不像”的依据正确
- 再进入 policy optimization

### 5.2 防 reward hacking

RL 最大风险不是“不提升”，而是“学会钻 reward 空子”。

典型风险：
- 更戏剧化
- 更锐利，但更假
- 更像表演版曲曲
- 更模板化地输出高分结构

因此必须同步监控：
- naturalness
- templaticness
- blandness
- OOC

### 5.3 保留 benchmark 回归

每轮 RL 更新后，都必须跑完整 benchmark：

- normal_qa
- multi_turn_followup
- adversarial
- cross_topic
- ooc_trap

任何一个关键 benchmark 类别退化，都不能直接接受模型。

### 5.4 小步试验

RL 不要大步更新。

建议：
- 小 batch
- 小步数
- 高频评测
- 高频人工抽检

### 5.5 人工抽检重点

每轮 RL 后至少抽检：

- 长对话 20~30 段
- 高压样本 20 条
- OOC trap 20 条

重点看：
- 是否更稳
- 是否更假
- 是否更会表演
- 是否更像“奖惩优化后的模仿秀”

---

## 6. 训练实验如何设计

## 6.1 baseline 设计

至少做 3 组实验：

### Exp-1：DPO 模型作为对照组
- 不做 RL
- 用作全部 RL 实验基线

### Exp-2：turn-level reward RL
- 只优化局部 reward
- 看单轮是否更像，但可能不足以提升长对话稳定性

### Exp-3：turn-level + conversation-level reward RL
- 同时加入整段对话全局奖励
- 验证是否更能改善长期一致性

## 6.2 reward 头 ablation

至少比较：

1. 只用 style + structure
2. style + structure + value
3. style + structure + value + multi_turn consistency
4. 是否加入 blandness / templatic penalty

## 6.3 关键对比维度

每轮实验比较：

1. reward model 准确性
2. multi_turn_consistency
3. value_alignment
4. user_intent_hit
5. OOC rate
6. blandness / templaticness
7. 人工主观自然度

## 6.4 实验记录模板

每个实验记录：

- 实验编号
- DPO 基座版本
- reward model 版本
- reward 头设置
- turn-level / conversation-level 权重
- 训练步数
- benchmark 总分
- multi_turn_consistency
- value_alignment
- user_intent_hit
- ooc_rate
- blandness
- templaticness
- 主观审查结论

## 6.5 推荐实验顺序

### 第 1 轮
- 先训练并验证 reward model
- 不直接上 policy RL

### 第 2 轮
- 小规模 turn-level reward RL
- 观察局部收益与副作用

### 第 3 轮
- 加入 conversation-level reward
- 重点验证长期一致性是否改进

---

## 7. 阶段 3 的交付物

阶段 3 完成时，至少交付：

1. 一版 reward model
2. 一版 RL 后 persona 模型
3. 一份 reward model 评测报告
4. 一份 RL 前后 benchmark 对比报告
5. 一份 reward hacking / 假模仿分析报告

---

## 8. 阶段 3 完成标准

本阶段完成，至少要满足：

1. 长对话一致性明显优于 DPO baseline
2. 价值观稳定性进一步提升
3. OOC rate 不升
4. 模板化率不升
5. 人工评测没有明显“更假”的问题

如果 RL 带来的收益不稳定，或副作用明显，应停止在 DPO 阶段作为最终版本。
