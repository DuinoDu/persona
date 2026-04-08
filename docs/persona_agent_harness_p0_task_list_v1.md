# Persona Agent Harness P0 工程任务拆解（曲曲项目）

## 1. 文档目的

把 `docs/persona_agent_harness_priority_v1.md` 里的 **P0 需求** 拆成可执行的工程任务清单，并结合当前代码库给出：
- 现状
- 缺口
- 任务拆分
- 文件落点
- 依赖关系
- 验收标准

本文默认当前系统边界为：
- **Web 控制面在本地运行**
- **模型推理在 H20 运行**
- **长任务通过 tmux 托管**
- **现有 `player` 为主控制台，不另起新系统**

---

## 2. 当前代码现状（基线）

## 2.1 已经具备的能力

### 数据模型已存在
当前 Prisma 已有：
- `InferHost`
- `ModelDeployment`
- `EvalSuite`
- `EvalRun`
- `LiveSession`
- `LiveTurn`
- `ArenaJudgment`

文件：
- `packages/player/prisma/schema.prisma`

### 在线 / 离线推理基础链路已存在
当前已有：
- 离线 batch eval runner
  - `scripts/evals/run_batch_chat_eval_py312.sh`
- 在线 live service runner
  - `scripts/evals/run_live_chat_service_py312.sh`
  - `scripts/evals/live_chat_service_qwen35_9b.py`
- 远端 H20 编排辅助
  - `packages/player/src/lib/remoteJobs.ts`

### 控制面 UI 已存在
当前已有页面：
- `/admin/evals`
- `/admin/evals/live`
- `/admin/evals/runs/new`
- `/admin/evals/runs/[id]`
- `/admin/evals/arena`

### Live 基础多轮链路已存在
当前已有：
- 启动 / 停止 / 健康检查接口
- chat / stream 接口
- live session / live turns 持久化
- 基础 service debug 展示

---

## 2.2 当前主要缺口

### 缺口 A：没有统一的 Persona Runtime Contract
现在 deployment 上只有：
- `systemPromptFile`
- `baseModelPath`
- `adapterPath`
- `defaultDevice`

但缺少：
- prompt version 概念
- generation config version 概念
- context builder version 概念
- 统一的 request signature

结果：
- 同一个 deployment 在 online / offline 下不可严格追溯
- 无法明确知道某条输出到底用了什么 prompt / config / context 规则

### 缺口 B：没有独立的 Context Builder 模块
当前 live `chat` / `stream` route 里存在重复逻辑：
- `splitStableTurns(...)`
- `messages` 直接现场拼装

但缺少：
- 统一上下文构建模块
- token budget 管理
- summary slot
- persona profile slot
- 可复用的 trim report

结果：
- online / offline 容易继续分叉
- 长对话会越跑越慢
- 无法系统调试“上下文是怎么被裁掉的”

### 缺口 C：trace 不完整
当前只记录：
- live turn 的 `rawJson`
- deployment 的 health / error
- eval run 的 resultJson

但缺少：
- final messages 持久化
- prompt / config / builder 版本记录
- trim / summary / retrieval 说明
- per-turn / per-case trace

结果：
- 坏例无法精确归因
- 无法比较“同 case 在两版 prompt 下到底输入差在哪”

### 缺口 D：评测闭环不完整
虽然已有：
- offline runs
- live sessions
- arena judgments

但缺少：
- 固定 eval suite 的分层定义
- 标准化人工标签口径
- bad case 导出为训练数据
- 从 live bad turn 回流到 SFT / preference 样本

### 缺口 E：online / offline 共享协议不够彻底
现在两边虽然都能跑，但还没有明确做到：
- 统一 request schema
- 统一 generation config schema
- 统一 trace schema
- 统一 runtime identity

---

## 3. P0 工程拆解总览

P0 拆成 6 个 Workstream：

1. **WS0 Runtime Contract**
2. **WS1 Context Builder**
3. **WS2 Unified Inference Protocol**
4. **WS3 Trace & Observability**
5. **WS4 Eval Suite & Human Labeling**
6. **WS5 Bad Case Export / Data Flywheel MVP**

建议执行顺序：

```text
WS0 -> WS1 -> WS2 -> WS3 -> WS4 -> WS5
```

原因：
- 没有 WS0/1/2，运行链路不可复现
- 没有 WS3，坏例不可解释
- 没有 WS4/5，评测结果不可沉淀

---

# 4. Workstream 详细拆解

## WS0. Runtime Contract（统一推理契约）

## 目标
为每一次 persona 推理建立一个 **统一、可追溯、可比较** 的推理签名。

---

## WS0-1. 定义 Runtime Signature

### 任务
定义一个稳定的 `runtime signature`，至少包含：
- `deployment_id`
- `base_model_path`
- `adapter_path`
- `prompt_version`
- `generation_config_version`
- `context_builder_version`
- `runner_kind`
- `service_mode`

### 建议落点
- 文档：`docs/persona_agent_harness_priority_v1.md`（补引用）
- 代码：`packages/player/src/lib/remoteJobs.ts`
- 新增：`packages/player/src/lib/personaRuntime.ts`

### 产出
- `buildRuntimeSignature(...)`
- `RuntimeSignature` TypeScript 类型
- signature hash 或 stable JSON 表达

### 验收
- 任意一次 online / offline 推理都能拿到一个完整 runtime signature

---

## WS0-2. 引入 Prompt Version / Generation Config Version

### 任务
不要只靠 `systemPromptFile` 字符串，要引入可版本化配置。

### 最小方案
先不一定上复杂 UI，可先用 DB / JSON 方式：
- `PromptVersion`
- `GenerationConfigProfile`
- `ContextBuilderProfile`

### 建议 schema 变更
在 Prisma 中新增：
- `PromptVersion`
- `GenerationConfigProfile`
- `ContextBuilderProfile`

并让 `ModelDeployment` 指向默认版本。

### 建议落点
- `packages/player/prisma/schema.prisma`
- `packages/player/src/app/api/infer/deployments/*`
- `packages/player/src/lib/personaRuntime.ts`

### 验收
- deployment 不再只表示“模型路径”，还要表示“默认运行配置”

---

## WS0-3. 统一推理请求结构

### 任务
定义 online / offline 共用的推理请求结构：

```ts
interface PersonaInferenceRequest {
  runtimeSignature: RuntimeSignature;
  messages: { role: string; content: string }[];
  generation: {
    maxNewTokens: number;
    doSample: boolean;
    temperature: number;
    topP: number;
  };
  traceMeta?: Record<string, unknown>;
}
```

### 建议落点
- `packages/player/src/lib/personaRuntime.ts`
- `packages/player/src/lib/remoteJobs.ts`
- `scripts/evals/live_chat_service_qwen35_9b.py`
- `scripts/evals/batch_chat_eval_qwen35_9b.py`

### 验收
- offline batch case 与 online live turn 最终都能归一为相同请求结构

---

## WS0 小结
这是 P0 的起点。没有这个层，后面做 trace 和 compare 都会乱。

---

## WS1. Context Builder（统一上下文构建器）

## 目标
把当前散落在 route 里的消息清洗和拼装逻辑，收敛成一个独立模块，并加入 **budget / summary / debug report**。

---

## WS1-1. 抽出 Context Builder 模块

### 任务
新建统一模块，接管当前 route 中的：
- orphan 清理
- turn 稳定化
- final messages 拼装

### 建议接口
```ts
interface BuildPersonaContextInput {
  turns: Array<{ id?: string; role: string; content: string }>;
  nextUserMessage?: string;
  systemPrompt?: string | null;
  summary?: string | null;
  maxInputTokens?: number;
  reserveOutputTokens?: number;
}

interface BuildPersonaContextOutput {
  messages: Array<{ role: string; content: string }>;
  stableTurnIds: string[];
  orphanTurnIds: string[];
  estimatedPromptTokens: number | null;
  trimReport: Record<string, unknown>;
}
```

### 建议落点
- 新增：`packages/player/src/lib/personaContextBuilder.ts`

### 需要替换的调用点
- `packages/player/src/app/api/evals/live/sessions/[id]/chat/route.ts`
- `packages/player/src/app/api/evals/live/sessions/[id]/stream/route.ts`
- `packages/player/src/app/api/evals/runs/route.ts` 对应 offline case 组装逻辑

### 验收
- live chat / stream 不再自己手写 `splitStableTurns`
- 所有推理入口统一走 `buildPersonaContext(...)`

---

## WS1-2. 加入 Token Budget 与裁剪策略

### 任务
第一版不用做复杂 summarizer，但必须加：
- prompt token 估算
- 预算超限时的裁剪策略
- 为输出预留 token budget

### 第一版建议策略
优先保留：
1. system prompt
2. summary slot（若有）
3. 最近 N 轮稳定对话
4. 当前 user message

### 建议落点
- `packages/player/src/lib/personaContextBuilder.ts`
- `scripts/evals/live_chat_service_qwen35_9b.py`（可选：增加 `/tokenize` 或 metadata 支持）

### 验收
- 长 session 时不再盲目把所有历史塞给模型
- trace 可看到本次裁掉了哪些 turn

---

## WS1-3. 引入 Summary Slot（占位版）

### 任务
P0 不要求自动 summary 生成器，但要求 context builder 支持一个明确的 summary 注入槽位。

### 最小实现
- `LiveSession.summaryText` 或类似字段
- `Eval case.summary` 可选字段
- 构建消息时把 summary 作为一条 system/developer 辅助信息注入

### 建议落点
- `packages/player/prisma/schema.prisma`
- `packages/player/src/lib/personaContextBuilder.ts`
- `packages/player/src/app/api/evals/live/sessions/*`

### 验收
- context builder 支持 summary 输入并进入 final messages

---

## WS1-4. Persona Profile Slot（占位版）

### 任务
P0 先不做复杂 memory，但需要给“结构化用户画像/会话画像”留出注入点。

### 最小实现
支持传入：
- user profile snapshot
- scenario / evaluation target

### 验收
- 不改主协议即可在 P1 接入 structured memory

---

## WS2. Unified Inference Protocol（统一在线/离线推理协议）

## 目标
让 H20 上的 offline batch infer 与 online live infer 在“输入协议、运行状态、trace 输出”上统一。

---

## WS2-1. 统一 generation config schema

### 任务
把当前 scattered 的：
- maxNewTokens
- doSample
- temperature
- topP

统一为一个 schema，并在 online / offline 两边共用。

### 建议落点
- `packages/player/src/lib/personaRuntime.ts`
- `packages/player/src/app/api/evals/runs/route.ts`
- `packages/player/src/app/api/evals/live/sessions/[id]/chat/route.ts`
- `packages/player/src/app/api/evals/live/sessions/[id]/stream/route.ts`
- `packages/player/src/components/evals/LiveInferConsole.tsx`
- `packages/player/src/components/evals/CreateEvalRunForm.tsx`

### 验收
- generation config 在前后端、online/offline 使用同一类型

---

## WS2-2. 统一 H20 runner 输入协议

### 任务
当前 live service 和 batch eval 都在 H20 上跑，但输入格式和 trace 产出可能不同。要统一。

### 需要完成
- batch eval case 转 `PersonaInferenceRequest`
- live turn 转 `PersonaInferenceRequest`
- H20 侧记录收到的 request metadata

### 建议落点
- `scripts/evals/batch_chat_eval_qwen35_9b.py`
- `scripts/evals/live_chat_service_qwen35_9b.py`
- `packages/player/src/lib/remoteJobs.ts`

### 验收
- 同样的 `messages + generation` 输入，online/offline 结果差异仅来自推理模式，而不是协议差异

---

## WS2-3. 统一状态与错误模型

### 任务
为在线服务和离线任务定义统一状态字段。

### 建议状态
- `draft`
- `queued`
- `starting`
- `running`
- `running_service`
- `succeeded`
- `failed`
- `failed_launch`
- `error`
- `stopped`

### 建议落点
- `packages/player/src/lib/remoteJobs.ts`
- `packages/player/src/lib/evalAdmin.ts`
- 相关 API routes

### 验收
- 前端无需根据不同 API 猜状态语义

---

## WS2-4. 统一日志与 artifact 路径约定

### 任务
把 live / offline 的日志、状态、输出目录约定整理清楚，并写成工具函数。

### 当前已有基础
- `buildOfflineEvalArtifacts(...)`
- `buildLiveServiceArtifacts(...)`

### 需要补足
- trace 输出目录
- request payload dump 路径
- exported bad case 路径

### 建议落点
- `packages/player/src/lib/remoteJobs.ts`
- 新增：`packages/player/src/lib/personaArtifacts.ts`

### 验收
- 任何一个 run / session / trace / export 都能按约定路径落盘或定位

---

## WS3. Trace & Observability（可观测性）

## 目标
让每一条模型输出都不是黑盒。

---

## WS3-1. 增加 InferenceTrace 数据模型

### 任务
新增可持久化的 trace 模型。

### 建议 schema
新增：
- `InferenceTrace`
- 可选：`InferenceTraceEvent`

最少字段：
- source type（offline_case / live_turn）
- source id
- runtime signature
- final messages json
- generation config json
- estimated prompt tokens
- generated tokens
- ready wait ms
- first token latency ms
- total latency ms
- trim report json
- summary snapshot json
- output text
- raw output json
- remote log path
- error

### 建议落点
- `packages/player/prisma/schema.prisma`

### 验收
- 每个 live assistant turn 和每个 offline case 至少对应一条 trace

---

## WS3-2. 在 live chat / stream 中记录 trace

### 任务
把当前请求中的关键信息写入 `InferenceTrace`。

### 建议落点
- `packages/player/src/app/api/evals/live/sessions/[id]/chat/route.ts`
- `packages/player/src/app/api/evals/live/sessions/[id]/stream/route.ts`

### 验收
- 可以从 live turn 反查本轮发送给模型的最终 messages

---

## WS3-3. 在 offline eval 中记录 per-case trace

### 任务
不能只记录 run summary，要能看每个 case 的 trace。

### 方案
- batch runner 输出 `cases/*.json`
- 控制面读取并写入 DB 或按需解析

### 建议落点
- `scripts/evals/batch_chat_eval_qwen35_9b.py`
- `packages/player/src/app/api/evals/runs/[id]/route.ts`
- 新增：`packages/player/src/lib/evalArtifacts.ts` 扩展

### 验收
- eval run 详情页至少能下钻到单 case 输入/输出/trace

---

## WS3-4. 增加 Trace Viewer UI

### 任务
新增最小 trace 查看能力。

### UI 至少支持
- 看 final messages
- 看 generation config
- 看 trim report
- 看 output / raw output
- 看 latency / token 指标
- 看关联 run / session / deployment

### 建议落点
- 新增页面：
  - `packages/player/src/app/admin/evals/traces/[id]/page.tsx`
- 或先挂在：
  - run detail page
  - live session panel

### 验收
- 评测人员不用 SSH 就能看推理输入与关键指标

---

## WS4. Eval Suite & Human Labeling（评测集与人工标注）

## 目标
把“凭感觉测”收敛成一个可重复执行、可比较的评测流程。

---

## WS4-1. 固化 Eval Suite 目录规范

### 任务
定义曲曲项目第一版固定 eval suite 规范。

### 推荐 slice
- `opening`
- `comment`
- `call_short`
- `call_long`
- `adversarial`
- `followup`
- `memory_consistency`

### 每条 case 最少字段
- `case_id`
- `slice`
- `messages`
- `expected_focus`
- `notes`
- `summary`（可选）

### 建议落点
- `data/evals/suites/...`
- `docs/persona_eval_suite_spec_v1.md`

### 验收
- 第一版 suite 至少有一套小而硬的固定 case 集

---

## WS4-2. 统一人工评分维度定义

### 任务
为人工评测建立统一口径。

### P0 评分维度建议
- `persona_consistency`
- `diagnosis_quality`
- `actionability`
- `multi_turn_stability`
- `safety_boundary`

### P0 failure tags 建议
- `style_drift`
- `vague_comfort`
- `no_diagnosis`
- `no_followup`
- `forgot_context`
- `too_harsh`
- `too_short`
- `leakage`

### 建议落点
- 文档：`docs/persona_human_eval_rubric_v1.md`
- 前端：`/admin/evals/arena`
- live panel 增加最小打标签能力（可选）

### 验收
- 至少 2 个评测人对同一批 case 的标签口径大致一致

---

## WS4-3. 离线 run 结果页增强

### 任务
当前 run detail 偏 run 级别，P0 需要补 case 级别结果浏览。

### 最小功能
- case 列表
- case 输出预览
- case trace 链接
- bad case 标记入口

### 建议落点
- `packages/player/src/app/admin/evals/runs/[id]/page.tsx`
- `packages/player/src/app/api/evals/runs/[id]/route.ts`

### 验收
- 跑完一个 eval run 后，能直接在页面中浏览坏例

---

## WS4-4. Live Session 人工标注入口

### 任务
在 live session 中增加最小标注入口。

### 最小能力
- 给某一轮 assistant turn 打标签
- 标记为 bad case
- 添加人工修订备注

### 建议落点
- `packages/player/src/components/evals/LiveInferConsole.tsx`
- 新增 API：`packages/player/src/app/api/evals/live/turns/[id]/labels/route.ts`

### 验收
- live 试聊中发现坏回复后，不需要额外复制粘贴到别处再标注

---

## WS5. Bad Case Export / Data Flywheel MVP（数据回流）

## 目标
让坏例不只是“看过了”，而是能进入下一轮训练数据。

---

## WS5-1. 定义导出格式

### 任务
支持至少两类导出：

#### SFT candidate
```json
{
  "source": "live_turn | offline_case",
  "input_messages": [...],
  "model_output": "...",
  "edited_target": "...",
  "tags": [...],
  "metadata": {...}
}
```

#### Preference pair candidate
```json
{
  "source": "arena | live_turn | offline_case",
  "input_messages": [...],
  "chosen": "...",
  "rejected": "...",
  "tags": [...],
  "metadata": {...}
}
```

### 建议落点
- 文档：`docs/persona_data_export_spec_v1.md`
- 新增：`packages/player/src/lib/personaExport.ts`

### 验收
- 可以从 UI 或 API 拿到结构化导出文件

---

## WS5-2. 增加 Bad Case / Export 数据模型

### 任务
新增最小数据模型，用于存储标记和导出状态。

### 建议 schema
新增：
- `BadCase`
- `TrainingExport`

### 验收
- 一个 live turn / offline case 可被标记、复查、导出

---

## WS5-3. 从 offline / live / arena 三入口导出

### 任务
支持三种来源：
- offline eval case
- live turn
- arena judgment

### 建议落点
- `packages/player/src/app/api/evals/runs/...`
- `packages/player/src/app/api/evals/live/...`
- `packages/player/src/app/api/evals/arena/judgments/route.ts`

### 验收
- 三种来源的数据最终能进入同一导出格式

---

## WS5-4. 导出文件落盘与下载

### 任务
导出的文件要有统一路径、命名和下载入口。

### 建议目录
- `artifacts/evals/exports/{date}/{export_id}.jsonl`

### 建议落点
- `packages/player/src/lib/personaArtifacts.ts`
- `packages/player/src/lib/personaExport.ts`
- 对应下载 API / 页面

### 验收
- 导出后可以直接拿给训练脚本消费

---

# 5. 任务依赖关系

## 强依赖顺序

### 第一层：运行时统一
- WS0 Runtime Contract
- WS1 Context Builder

### 第二层：协议打通
- WS2 Unified Inference Protocol

### 第三层：可观测性
- WS3 Trace & Observability

### 第四层：评测闭环
- WS4 Eval Suite & Human Labeling
- WS5 Bad Case Export

---

# 6. 推荐实施阶段

## Phase A：先打地基
目标：统一 runtime identity 和 context builder

包含：
- WS0-1
- WS0-2
- WS0-3
- WS1-1
- WS1-2
- WS1-3

完成后收益：
- online / offline 输入开始可控
- 多轮历史开始可治理

## Phase B：打通推理协议 + trace
包含：
- WS2-1
- WS2-2
- WS2-3
- WS2-4
- WS3-1
- WS3-2
- WS3-3
- WS3-4

完成后收益：
- 坏例可以解释
- 系统可以做差异对比

## Phase C：补齐评测与回流
包含：
- WS4-1
- WS4-2
- WS4-3
- WS4-4
- WS5-1
- WS5-2
- WS5-3
- WS5-4

完成后收益：
- 评测结果可沉淀为训练数据
- 形成 P0 闭环

---

# 7. DoD（P0 完成定义）

满足以下全部条件，视为 P0 done：

1. online / offline 共用统一 runtime signature
2. live / batch 都通过统一 context builder 组装输入
3. 任一 live turn / offline case 可查看 final messages 与 generation config
4. 长会话具备 token budget 裁剪能力
5. 至少一套固定 eval suite 可批量运行并浏览 case 结果
6. live session 支持对某一轮打标签
7. bad case 可导出为 SFT candidate 或 preference pair candidate
8. 评测人员不用 SSH 即可在 UI 中查看大部分关键问题定位信息

---

# 8. 当前最值得立即开工的 10 个任务

如果要今天开始排期，建议优先开这 10 个：

1. 新建 `personaRuntime.ts`，定义 runtime signature 与 generation config 类型
2. 新建 `personaContextBuilder.ts`，接管 `splitStableTurns + messages 拼装`
3. 把 live chat route 接到 context builder
4. 把 live stream route 接到 context builder
5. 给 Prisma 增加 `InferenceTrace`
6. 在 live chat / stream 中落 trace
7. 给 offline batch 输出加 per-case trace 文件
8. 设计并固化 eval suite JSON schema
9. 设计并固化 human eval rubric 文档
10. 设计 bad case export JSONL 格式

---

# 9. 一句话结论

对曲曲项目来说，P0 的核心不是“再加一个更聪明的 agent 层”，而是先把：

> **推理输入统一、上下文治理、trace 可见、坏例可回流**

这四件事做成工程能力。
