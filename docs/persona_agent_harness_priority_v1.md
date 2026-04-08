# Persona Agent Harness 优先级分层与 P0 任务文档（曲曲项目）

## 1. 文档目的

本文件从“曲曲”persona 多轮咨询项目的实际目标出发，对 Agent Harness 需求进行 P0 / P1 / P2 / P3 分层，并将 **P0 需求** 落成一份可直接执行的任务文档。

这里的 Agent Harness 不是通用 Agent 平台，而是：

> 一套围绕 **persona 多轮对话运行、评测、观测、数据回流** 的系统。

其首要目标不是“更会用工具”，而是：

1. 让曲曲在多轮对话中 **稳定像曲曲**
2. 让线上 / 线下推理 **可控、可复现、可比较**
3. 让 bad case 可以 **沉淀并回流到下一轮训练**

---

## 2. 优先级划分原则

### P0
没有这些，系统虽然能“出字”，但无法支撑可靠的 persona 多轮评测与迭代；或者结果不可复现、不可解释、不可沉淀。

### P1
显著提升效果、效率或评测可信度，但不阻塞第一版闭环跑通。

### P2
用于提升长期质量上限、降低人力成本、增强可扩展性。

### P3
偏长期探索项或锦上添花项，对当前主线收益较远。

---

## 3. 需求优先级分组

## P0：必须先落地的基础能力

### P0-1. Persona Runtime Contract（人格运行时契约）
必须明确定义每次推理到底由哪些输入组成：
- system prompt / persona policy 的版本化管理
- 会话消息拼装规则
- generation config 版本化
- 部署 / checkpoint / adapter 版本记录
- online / offline 共享同一套推理输入协议

**要解决的问题：**
- 同一个模型不同入口表现不一致
- 无法追溯“这次输出到底喂了什么”
- prompt、参数、checkpoint 漂移导致结果不可复现

### P0-2. Session State & Context Builder（会话状态与上下文构建器）
必须把“多轮对话输入给模型前”的处理逻辑产品化：
- 历史消息清洗与合法性检查
- orphan turn / 重复 turn 防御
- 最近轮次保留策略
- 长对话摘要策略
- 关键用户画像槽位提取后的注入规则
- context budget 控制

**要解决的问题：**
- 多轮越长越乱
- 重复问、忘前文、前后矛盾
- 上下文超长导致延迟升高、效果退化

### P0-3. Unified Inference Orchestrator（统一推理编排层）
必须支持：
- H20 上离线 batch infer
- H20 上在线 live infer
- 同一 deployment 在 offline / online 下共用 runner 协议
- readiness / health / tmux / log / output / status 统一管理

**要解决的问题：**
- 在线、离线两套逻辑分裂
- 服务状态不可见，错误难定位
- 实验结果和线上表现脱节

### P0-4. Eval Loop MVP（评测闭环最小集）
必须具备：
- 固定离线评测集
- 在线多轮 live session
- 人工打分与标签体系
- checkpoint / prompt / config 对比
- bad case 导出

**要解决的问题：**
- 只能凭感觉判断模型好坏
- 无法知道“提升了什么 / 退化了什么”
- 评测结果无法反哺训练

### P0-5. Trace & Observability（推理可观测性）
每次样本 / 每轮对话至少要记录：
- model / checkpoint / adapter
- prompt version
- messages 最终拼装结果
- memory / summary / retrieval 命中内容
- latency（ready wait / first token / full completion）
- input / output token
- error 类型与远端日志引用

**要解决的问题：**
- 输出不好但不知道坏在哪一步
- 无法区分是模型问题、prompt 问题还是上下文拼装问题
- 线上问题无法快速复盘

### P0-6. Data Flywheel MVP（数据回流最小集）
必须支持：
- 从线上 / 线下评测中筛 bad case
- 记录 failure tag
- 支持人工改写 target answer / preferred answer
- 导出为下一轮 SFT / preference 数据

**要解决的问题：**
- 每轮评测都在重复发现同样的问题
- insight 无法转成训练数据

---

## P1：强烈建议第二阶段落地

### P1-1. Structured Memory
- 用户画像槽位抽取
- 重要事实 / 风险点 / 行动项记忆
- 会话摘要自动更新
- 跨轮冲突检测

### P1-2. Retrieval-Augmented Persona Support
- 相似 case 检索
- style few-shot 与 content few-shot 分离
- opening / comment / call 分场景示例注入

### P1-3. Judge-based Auto Eval
- judge model 自动打分
- 按维度自动归因：style drift / vague comfort / no diagnosis / weak actionability
- 与人工标注对齐校准

### P1-4. Experiment Compare Center
- 多 checkpoint / 多 prompt / 多 config 横向对比
- 按 slice 聚合统计
- 输出 best / worst case 集合

---

## P2：提升上限与规模化能力

### P2-1. Dialogue Strategy Layer
- opening / probing / diagnosis / advice / push / close 阶段建模
- 追问策略与推进策略控制

### P2-2. Long-term Memory
- 跨 session 用户画像
- 长周期用户状态演化
- 老用户持续对话一致性

### P2-3. Synthetic / Counterfactual Data Engine
- 自动生成 hard negative
- 自动扩充诱导、对抗、追问类样本
- 自动产出 preference pair 候选

### P2-4. Insight-to-Training Automation
- 按失败模式自动聚类
- 自动生成下一轮数据标注任务与训练建议

---

## P3：长期探索项

### P3-1. Multi-agent Persona Architecture
- planner / responder / critic / memory manager 分角色协作

### P3-2. Tool-use Persona Agent
- 日程、资料检索、个人数据库、外部知识融合

### P3-3. Multi-modal Persona Harness
- 语音、视频、直播场景联动
- prosody / 情绪 / 节奏联合评测

### P3-4. Self-play / Simulated User Arena
- 用户模拟器自动生成长对话
- 大规模 stress test

---

# 4. P0 任务文档

## 4.1 任务概述

在现有 `player + H20` 架构上，为曲曲项目补齐一套 **Persona Agent Harness P0**，使其能够稳定支撑：
- 在线多轮 persona 对话
- 离线批量 persona 评测
- 可复现的推理输入组装
- 可观察的运行日志与 trace
- bad case 回流为下一轮训练数据

P0 的目标不是做“高级智能体”，而是先把 **运行时、评测、观测、回流** 这条最短闭环跑通。

---

## 4.2 目标与成功定义

### 主要目标

完成一版面向曲曲项目的 Agent Harness P0，使团队可以对“某个模型 / 某个 checkpoint / 某个 prompt 版本”进行可靠评测，并能够从结果中产出下一轮训练数据。

### 成功标准

满足以下条件即视为 P0 完成：

1. **同一 deployment 可同时用于 offline batch infer 与 online live infer**
2. **每次推理都能追溯完整输入构成**，包括 prompt、history、summary、generation config、deployment 信息
3. **多轮会话存在统一的 context builder**，并具备长上下文预算控制能力
4. **至少有一套固定离线评测集**，可以批量跑并产出结构化结果
5. **至少有一套在线 live session 评测入口**，支持人工多轮体验和标注
6. **bad case 可以被打标签并导出为训练数据候选**
7. **关键错误可通过日志 / trace 快速定位**，而不是只看到“回复不好”

---

## 4.3 范围

### 包含范围

#### A. Persona Runtime Contract
- 定义 `deployment + prompt_version + generation_config + context_builder_version` 的唯一推理签名
- online / offline 共用同一消息组装协议
- 将最终发送给模型的消息体持久化或可重建

#### B. Context Builder
- 历史 turn 合法性校验
- trailing orphan user 清理
- 重复 turn / 脏 turn 防御
- 最近轮次保留
- 长历史摘要插入
- token budget 估算与裁剪

#### C. Inference Orchestrator
- H20 tmux 启动、状态检查、健康检查、日志读取
- offline eval job runner
- online live service runner
- 统一错误码 / 状态字段

#### D. Eval Loop
- 固定评测集管理
- 离线 eval run 页面或结果页
- 在线 live session 页面
- 基础人工标签：persona / diagnosis / actionability / stability / safety / style_drift / vague_comfort / no_followup

#### E. Trace & Observability
- 推理 trace 查看
- latency / tokens / input payload 可见
- 远端日志链接或摘要

#### F. Data Flywheel MVP
- 从 eval case / live turn 标记 bad case
- 导出 SFT candidate / preference pair candidate
- 保留 source metadata

### 不包含范围

P0 不包含以下内容：
- 跨 session 长期记忆
- 自动相似 case 检索
- judge model 自动打分闭环
- 多 agent 分工
- 工具调用编排
- 语音 / 视频多模态能力
- 自动生成训练建议全文报告

---

## 4.4 输入

### 输入 1：现有推理基础设施
- 格式：代码 / shell / Python / tmux 运行约定
- 来源：项目现有实现
- 说明：包括 H20 上 live service、batch eval runner、player 控制面

### 输入 2：现有评测后台
- 格式：Next.js + Prisma + SQLite/Postgres 数据模型
- 来源：项目现有实现
- 说明：包括 deployment、eval run、live session、arena 等模块

### 输入 3：固定评测数据
- 格式：JSON / JSONL / parts 数据集
- 来源：项目已有 `data/03_parts`、评测样本、人工整理 case
- 说明：P0 至少需要一套稳定、可重复运行的 suite

### 输入 4：persona 运行配置
- 格式：Markdown / JSON / DB records
- 来源：人工配置
- 说明：包含 system prompt、persona policy、generation config、context builder config

### 输入 5：人工评测标签体系
- 格式：枚举标签与评分维度定义
- 来源：产品 / 训练侧共同定义
- 说明：用于统一 bad case 标注口径

---

## 4.5 预期输出

### 输出 1：P0 架构说明文档
- 格式：Markdown
- 完整程度：描述 runtime contract、context builder、orchestrator、eval loop、trace、data export 的边界与数据流

### 输出 2：统一推理签名与消息协议
- 格式：代码 + 文档
- 完整程度：online / offline 共用，并可落库或重建

### 输出 3：Context Builder MVP
- 格式：代码 + 配置
- 完整程度：可处理历史清洗、摘要插入、budget 控制

### 输出 4：Eval Loop MVP
- 格式：代码 + 页面 + runner
- 完整程度：支持离线批量与在线多轮，并可打标签

### 输出 5：Trace Viewer / Result View
- 格式：页面 + API
- 完整程度：可查看每次推理关键上下文与性能指标

### 输出 6：Bad Case Export
- 格式：JSON / JSONL
- 完整程度：可导出为下一轮训练样本候选

---

## 4.6 约束与假设

### 约束
- Web 控制面运行在本地环境
- 模型推理运行在 H20
- 长时任务必须通过 tmux 托管
- 不能假设在线服务永远秒级 ready，需要显式 readiness 处理
- 当前模型上下文虽大，但不能无限追加历史，必须有 budget 机制
- 人工评测资源有限，P0 必须先支持少量高价值 case 的高质量评测

### 假设
- 现有 `player` 后台会继续作为控制面，而不是另起一套新前端
- 现有 H20 推理 runner 会继续复用，而不是整体替换推理栈
- 离线与在线评测会共用 deployment registry
- 第一版以文本多轮对话为主，不处理语音实时链路

---

## 4.7 执行计划

### Step 1. 定义统一推理签名
产出一个稳定的 request identity：
- deployment_id
- model_path / adapter_path
- prompt_version
- generation_config_version
- context_builder_version
- eval_suite_id 或 live_session_id

要求：任何一次输出都能唯一追溯到上述组合。

### Step 2. 抽象 Context Builder
把在线 / 离线各处散落的 history 处理逻辑收敛成统一模块。

最小能力：
- 输入：raw turns + optional persona config + optional summary + budget
- 输出：final messages + debug metadata + trim report

至少实现：
- 非法 turn 过滤
- orphan user 清理
- 最近 N 轮保留
- summary slot 注入
- token budget 超限时裁剪

### Step 3. 统一 online / offline 的推理调用协议
- offline batch infer 与 live infer 共用相同 messages 生成逻辑
- generation 参数、stop、max_new_tokens、temperature 的来源统一
- 记录远端 tmux session、health、stderr/stdout 引用

### Step 4. 补齐 Trace 存储与展示
每次推理记录：
- final messages
- token estimate
- trim / summary 说明
- latency 指标
- output
- error 与远端日志位置

UI 至少要能：
- 看单条 case trace
- 看 live 某一轮 trace
- 对比两个输出的输入差异

### Step 5. 固化离线评测套件
为曲曲项目定义一套小而硬的 eval suite：
- opening 类
- comment 类
- 长 call 类
- 对抗 / 诱导类
- 连续追问类

每个 case 至少具备：
- case id
- 输入历史
- 评测目标
- slice 标签

### Step 6. 固化人工标注口径
先只保留少量高价值维度：
- persona consistency
- diagnosis quality
- actionability
- multi-turn stability
- safety / boundary
- failure tags

要求：
- 每个标签定义清楚“什么算命中”
- 不允许不同标注人理解完全不同

### Step 7. 打通 bad case 导出
允许从以下入口导出：
- offline eval case
- arena 对比 case
- live session 某一轮或某几轮

导出内容至少包括：
- input history
- model output
- preferred answer / edited answer（若有）
- tags
- prompt / config / model metadata

### Step 8. 建立 P0 验收样例集
选择一批高价值样例，覆盖：
- 像曲曲的基础风格
- 多轮不漂
- 面对错误前提会纠偏
- 建议不空泛
- 不忘前文

用于每次改 prompt / 改 context builder / 改 checkpoint 后回归检查。

---

## 4.8 验收标准

以下每项都必须是“通过 / 不通过”：

1. **统一推理签名可用**
   - 任意一条 offline / online 输出都能查到 model、checkpoint、prompt、config、context builder 版本

2. **online / offline 消息组装一致**
   - 对同一输入样本，两种入口生成的 final messages 结构一致

3. **长对话 budget 控制可工作**
   - 超长 session 不会无限堆历史；trace 中能看到裁剪或摘要结果

4. **离线 suite 可稳定批量运行**
   - 至少一套固定 eval suite 能完整跑通并生成结构化结果

5. **在线 live session 可稳定多轮运行**
   - 新建 session 后可连续进行多轮对话，且 transcript 与 trace 持久化正常

6. **trace 可用于定位问题**
   - 当出现坏例或报错时，可以通过 trace 判断问题发生在 prompt、history、summary、runner 或模型输出层

7. **bad case 可导出**
   - 至少能从一个 offline case 和一个 live turn 导出训练样本候选

8. **人工评测口径明确**
   - 至少 5 个核心维度和 5 个 failure tags 有明确定义，并在 UI 或文档中可见

---

## 4.9 风险与待澄清问题

### 风险
- 如果没有统一 context builder，后续加 memory / retrieval 会进一步失控
- 如果 trace 记录不完整，评测结果仍然无法解释
- 如果人工标签定义过宽，bad case 回流的数据质量会很差
- 如果不尽早处理长对话 budget，在线体验会随轮次迅速恶化

### 待澄清问题
- P0 是否需要直接支持“编辑模型回答后保存为 target answer” 的 UI
- P0 的 trace 是否允许持久化完整 prompt / messages，还是只存 hash + reconstructable config
- 离线 eval suite 第一版的标准规模是 20 条、50 条还是 100 条
- bad case 导出的首选训练格式是 SFT JSONL 还是 preference pair JSONL，还是两者都要

---

## 5. 建议执行顺序

如果按收益 / 风险比排序，建议按下面顺序推进：

1. 统一推理签名
2. 抽象 context builder
3. 统一 online / offline 推理协议
4. trace 存储与查看
5. 固化离线 suite
6. 固化人工标签
7. bad case 导出

原因：
- 没有 1~4，评测结果不可信
- 没有 5~7，评测结果不可沉淀

---

## 6. 一句话结论

曲曲项目的 Agent Harness，P0 不是“让模型更智能”，而是先建立：

> **可复现的 persona 运行时 + 可比较的评测闭环 + 可回流的数据接口。**

只有这三件事成立，后面的 memory、retrieval、judge、strategy layer 才值得继续加。
