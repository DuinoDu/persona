# 001_sft_task-list.md

> 目标：把 `001_sft.md` 落成一份可以直接执行、逐项勾选、跟踪进度的 SFT 阶段任务清单。
>
> 本清单覆盖 3 条主线：
> 1. 数据标注任务
> 2. 模型训练任务
> 3. 评测任务

---

## 0. 里程碑定义

### M0：SFT 数据可用
- `conversation_v1.jsonl` 和 `turn_sft_v1.jsonl` 有稳定版本
- schema/QC 通过
- train/dev/test/holdout 切分固定

### M1：SFT baseline 可训练
- 已完成首轮 baseline 训练
- 有完整训练日志和模型产物

### M2：SFT baseline 可评估
- 已完成离线评测
- 能判断是否进入阶段 2（DPO）

---

## 1. 任务总览

### 1.1 数据标注任务
- [ ] D1. 明确 SFT 数据版本目录与命名规范
- [ ] D2. 生成 `conversation_v1.jsonl` 初版
- [ ] D3. 生成 `turn_sft_v1.jsonl` 初版
- [ ] D4. 补齐 turn_sft 核心标签
- [ ] D5. 跑 schema + 规则 QC
- [ ] D6. 修复 fail/warn 并冻结数据版本
- [ ] D7. 做 train/dev/test/holdout 切分
- [ ] D8. 做数据分布统计与均衡检查
- [ ] D9. 构建 hard cases 子集

### 1.2 模型训练任务
- [ ] T1. 确定 SFT 基座模型、上下文长度、模板格式
- [ ] T2. 定义 system anchor v1
- [ ] T3. 实现 turn-only baseline 训练
- [ ] T4. 实现 turn + conversation 混合训练
- [ ] T5. 实现 curriculum 训练
- [ ] T6. 保存训练日志、checkpoint、配置
- [ ] T7. 汇总实验结果表

### 1.3 评测任务
- [ ] E1. 固定 SFT 阶段 benchmark 集
- [ ] E2. 实现自动推理评测脚本
- [ ] E3. 统计训练内指标（loss / ppl）
- [ ] E4. 统计行为指标（style / value / consistency / OOC）
- [ ] E5. 做人工抽检
- [ ] E6. 产出误差分析报告
- [ ] E7. 决策是否进入阶段 2

---

# 2. 数据标注任务

## D1. 明确 SFT 数据版本目录与命名规范

### 目标
给阶段 1 固定一版可重复使用的数据目录。

### 任务
- [ ] 建立目录：`data/05_annotations/sft_v1/`
- [ ] 固定文件：
  - [ ] `conversation_v1.jsonl`
  - [ ] `turn_sft_v1.jsonl`
  - [ ] `split_manifest.json`
  - [ ] `stats_summary.json`
  - [ ] `hard_cases.jsonl`
- [ ] 记录版本说明：`README.md`

### 验收
- [ ] 所有文件路径固定，不再临时命名
- [ ] 数据版本号可追溯

---

## D2. 生成 `conversation_v1.jsonl` 初版

### 目标
把 `call section` 转成 conversation 级训练样本。

### 任务
- [ ] 遍历 `data/03_transcripts/**/*_连麦.json`
- [ ] 将 sentence 合并为 turn
- [ ] 映射：`host -> persona`，`guest -> user`
- [ ] 填充 source/meta 基础字段
- [ ] 写入 `conversation_v1.jsonl`

### 必查项
- [ ] 每条 conversation 只来自一个 `call section`
- [ ] turn 已连续合并，不存在相邻同 speaker 未合并
- [ ] `topic_primary` 有初始值
- [ ] `train_split` 先允许占位，后续统一切分

### 验收
- [ ] conversation 样本可被 schema 校验通过

---

## D3. 生成 `turn_sft_v1.jsonl` 初版

### 目标
把 conversation 拆成 `history -> target_reply`。

### 任务
- [ ] 从 conversation 样本提取 persona turn
- [ ] 对每个 persona turn 构造一条 `turn_sft` 记录
- [ ] `history` 保留此前所有 turn
- [ ] `target_reply` 指向当前 persona 回复

### 必查项
- [ ] `history` 必须以 user 结束
- [ ] `target_reply` 必须是 host/persona 真实回复
- [ ] `target_reply.start/end` 与 source 对齐

### 验收
- [ ] turn_sft 样本可被 schema 校验通过

---

## D4. 补齐 turn_sft 核心标签

### 目标
让 `turn_sft` 满足训练最小要求。

### 必标字段
- [ ] `reply_type`
- [ ] `topic_primary`
- [ ] `difficulty`
- [ ] `user_emotion`
- [ ] `transcript_quality`

### 任务
- [ ] 先自动预标一版
- [ ] 人工抽检修正高频错误标签
- [ ] 对低置信度样本打回重标

### 验收
- [ ] 核心标签覆盖率 100%
- [ ] 抽检一致性达到可用水平

---

## D5. 跑 schema + 规则 QC

### 目标
确保训练前数据没有结构性错误。

### 任务
- [ ] 运行：`scripts/qc_annotation_records.py`
- [ ] 输出 summary / records / invalid
- [ ] 记录 fail/warn 数量

### 必查项
- [ ] schema_invalid = 0
- [ ] fail = 0
- [ ] warn 已知且可接受

### 验收
- [ ] QC 结果可归档到 `data/05_annotations/sft_v1/qc/`

---

## D6. 修复 fail/warn 并冻结数据版本

### 目标
得到可训练的数据冻结版本。

### 任务
- [ ] 修复全部 fail
- [ ] 逐类处理 warn：
  - [ ] turn overlap
  - [ ] topic 不确定
  - [ ] 标签边界模糊
- [ ] 生成冻结版 README
- [ ] 记录样本数与版本时间

### 验收
- [ ] 数据冻结后不再手工修改原文件
- [ ] 若更新，必须升版本号

---

## D7. 做 train/dev/test/holdout 切分

### 目标
固定阶段 1 切分，防止泄漏。

### 任务
- [ ] 以 conversation 为最小切分单位
- [ ] 同一 conversation 不跨 split
- [ ] 同一 episode 尽量不同时出现在 train 与 holdout
- [ ] 输出 `split_manifest.json`

### 建议比例
- [ ] train：70~80%
- [ ] dev：10~15%
- [ ] test：5~10%
- [ ] holdout：5~10%

### 验收
- [ ] 所有样本都有 split
- [ ] 无跨 conversation 泄漏

---

## D8. 做数据分布统计与均衡检查

### 目标
防止模型学偏。

### 任务
- [ ] 统计 `topic_primary` 分布
- [ ] 统计 `reply_type` 分布
- [ ] 统计 `difficulty` 分布
- [ ] 统计 `user_emotion` 分布
- [ ] 统计对话长度分布
- [ ] 识别极端高频类目

### 验收
- [ ] 输出 `stats_summary.json`
- [ ] 明确是否需要重采样

---

## D9. 构建 hard cases 子集

### 目标
提前补齐边角 case，降低 SFT 只学到平均回复。

### 任务
筛出以下类型样本：
- [ ] 用户前提错误
- [ ] 用户情绪强
- [ ] 连续追问 >= 3 轮
- [ ] 问题很混乱
- [ ] 明显诱导模型偏离风格

### 输出
- [ ] `hard_cases.jsonl`

### 验收
- [ ] hard cases 占训练样本的 10%~20% 可调

---

# 3. 模型训练任务

## T1. 确定 SFT 基座模型、上下文长度、模板格式

### 任务
- [ ] 选定基座模型
- [ ] 固定 tokenizer / chat template
- [ ] 固定 max context length
- [ ] 固定训练输入格式

### 验收
- [ ] 输出 `train_config_v1.yaml` 或等价配置文件

---

## T2. 定义 system anchor v1

### 目标
给训练提供统一 persona 行为锚点。

### 任务
- [ ] 写 1 版简洁 anchor
- [ ] 明确：
  - [ ] 遇到模糊问题先澄清/重构
  - [ ] 优先给框架，再给判断
  - [ ] 不做廉价鼓励
  - [ ] 保持现实主义/结果导向
- [ ] 固定为训练统一模板

### 验收
- [ ] 所有实验使用同一 anchor v1

---

## T3. 实现 turn-only baseline 训练

### 目标
先建立最小可用 baseline。

### 数据
- [ ] 仅使用 `turn_sft_v1.jsonl`

### 任务
- [ ] 准备训练数据 loader
- [ ] 只对 target_reply 算 loss
- [ ] 跑首轮训练
- [ ] 保存 checkpoint
- [ ] 保存 train/dev loss 曲线

### 输出
- [ ] `exp_sft_turn_only_v1/`

### 验收
- [ ] 能稳定收敛
- [ ] 有可推理模型

---

## T4. 实现 turn + conversation 混合训练

### 目标
增强多轮一致性。

### 数据
- [ ] turn_sft
- [ ] conversation

### 任务
- [ ] 按 60/25/15 设计混合采样
- [ ] conversation 样本转为训练格式
- [ ] 跑混合训练
- [ ] 与 turn-only 做对比

### 输出
- [ ] `exp_sft_mix_v1/`

### 验收
- [ ] 相比 turn-only，不降低单轮质量
- [ ] 多轮稳定性有提升趋势

---

## T5. 实现 curriculum 训练

### 目标
降低长对话漂移。

### 任务
- [ ] 定义短历史 bucket（1~2 轮）
- [ ] 定义中历史 bucket（3~5 轮）
- [ ] 定义长历史 bucket（5~10 轮）
- [ ] 分阶段训练或动态采样
- [ ] 跑 curriculum 实验

### 输出
- [ ] `exp_sft_curriculum_v1/`

### 验收
- [ ] 长上下文样本表现优于非 curriculum baseline

---

## T6. 保存训练日志、checkpoint、配置

### 目标
保证实验可复现。

### 任务
- [ ] 保存 config
- [ ] 保存 dataset version
- [ ] 保存训练日志
- [ ] 保存 checkpoint
- [ ] 保存推理参数

### 验收
- [ ] 任一实验可独立复跑

---

## T7. 汇总实验结果表

### 目标
把不同实验放到同一个比较表。

### 任务
- [ ] 记录实验编号
- [ ] 记录数据版本
- [ ] 记录样本数
- [ ] 记录训练参数
- [ ] 记录 loss / ppl / benchmark 指标
- [ ] 记录人工结论

### 输出
- [ ] `sft_experiment_summary.md`
- [ ] `sft_experiment_summary.csv`

---

# 4. 评测任务

## E1. 固定 SFT 阶段 benchmark 集

### 目标
建立统一评测入口。

### 任务
- [ ] 从 `benchmark_v1.jsonl` 中选出阶段 1 使用子集
- [ ] 覆盖：
  - [ ] normal_qa
  - [ ] multi_turn_followup
  - [ ] adversarial（少量）
  - [ ] cross_topic
- [ ] 固定 benchmark 版本

### 验收
- [ ] benchmark 不随实验临时变化

---

## E2. 实现自动推理评测脚本

### 目标
让每轮实验都能自动产出同一套指标。

### 任务
- [ ] 读取模型 checkpoint
- [ ] 跑 benchmark 推理
- [ ] 保存模型输出
- [ ] 保存评测结果 JSON

### 输出
- [ ] `eval_outputs/<exp_id>/`

---

## E3. 统计训练内指标（loss / ppl）

### 任务
- [ ] train loss
- [ ] dev loss
- [ ] perplexity / NLL
- [ ] 收敛速度
- [ ] 是否过拟合

### 验收
- [ ] 每个实验都有统一训练内指标

---

## E4. 统计行为指标

### 必做指标
- [ ] `style_similarity`
- [ ] `structure_similarity`
- [ ] `value_alignment`
- [ ] `multi_turn_consistency`
- [ ] `user_intent_hit`
- [ ] `ooc_rate`
- [ ] `templatic_rate`

### 任务
- [ ] 定义打分 rubric
- [ ] 自动打分或半自动评审
- [ ] 汇总分数

### 验收
- [ ] 不同实验可横向比较

---

## E5. 做人工抽检

### 目标
防止只看自动分数。

### 抽检规模
- [ ] 单轮：30~50 条
- [ ] 多轮：20~30 段
- [ ] 高压样本：20 条

### 检查点
- [ ] 是否像曲曲
- [ ] 是否答到点上
- [ ] 是否开始模板化
- [ ] 是否出现明显出戏

### 输出
- [ ] `manual_review_notes.md`

---

## E6. 产出误差分析报告

### 目标
明确阶段 1 剩余问题。

### 任务
- [ ] 收集失败 case
- [ ] 分类问题：
  - [ ] 太软
  - [ ] 太模板
  - [ ] 价值观漂移
  - [ ] 长对话失稳
  - [ ] 没答到点上
- [ ] 给出下一轮改进建议

### 输出
- [ ] `sft_error_analysis.md`

---

## E7. 决策是否进入阶段 2

### 目标
基于结果做 go / no-go 决策。

### 验收标准（来自 001_sft.md）
- [ ] dev loss 稳定收敛
- [ ] 单轮像不像达到可用水平
- [ ] 多轮 5 轮内不明显漂移
- [ ] OOC rate 低于当前 baseline
- [ ] 模板化率不上升

### 输出
- [ ] `sft_stage_gate.md`
- [ ] 结论：
  - [ ] 进入阶段 2
  - [ ] 继续迭代阶段 1

---

# 5. 建议执行顺序

## Week 1：数据可用
- [ ] D1
- [ ] D2
- [ ] D3
- [ ] D4
- [ ] D5
- [ ] D6

## Week 2：数据冻结 + baseline
- [ ] D7
- [ ] D8
- [ ] D9
- [ ] T1
- [ ] T2
- [ ] T3

## Week 3：混合训练 + curriculum
- [ ] T4
- [ ] T5
- [ ] T6
- [ ] T7

## Week 4：评测与决策
- [ ] E1
- [ ] E2
- [ ] E3
- [ ] E4
- [ ] E5
- [ ] E6
- [ ] E7

---

# 6. 最终交付物清单

## 数据侧
- [ ] `conversation_v1.jsonl`
- [ ] `turn_sft_v1.jsonl`
- [ ] `split_manifest.json`
- [ ] `stats_summary.json`
- [ ] `hard_cases.jsonl`
- [ ] QC 报告

## 训练侧
- [ ] `exp_sft_turn_only_v1/`
- [ ] `exp_sft_mix_v1/`
- [ ] `exp_sft_curriculum_v1/`
- [ ] 配置文件
- [ ] 实验结果表

## 评测侧
- [ ] benchmark 输出
- [ ] 自动评测结果
- [ ] 人工抽检记录
- [ ] 误差分析报告
- [ ] 阶段 gate 结论

---

# 7. 当前状态（初始化）

- [x] 已有 `001_sft.md`
- [x] 已有 annotation schema
- [x] 已有 annotation examples
- [x] 已有 annotation QC 脚本
- [ ] 尚未生成正式 `conversation_v1.jsonl`
- [ ] 尚未生成正式 `turn_sft_v1.jsonl`
- [ ] 尚未开始 SFT baseline 训练
- [ ] 尚未建立阶段 1 benchmark 流程
