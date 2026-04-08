# Persona Agent Harness P0 执行板（曲曲项目）

## 1. 目标

把 `persona_agent_harness_priority_v1.md` 与 `persona_agent_harness_p0_task_list_v1.md` 转成可执行的项目管理板，明确：
- 哪些任务必须串行冻结
- 哪些任务可以并行
- 第一批 subagents 的职责划分
- 当前推进状态

---

## 2. 串行前置（必须先冻结）

以下 4 项是并行开发的接口前提，必须先由主线统一口径：

1. `RuntimeSignature` 结构
2. `PersonaInferenceRequest` 结构
3. `BuildPersonaContextInput / Output` 结构
4. `InferenceTrace` 最小字段集合

### 当前冻结口径（v0）

#### RuntimeSignature
- `deploymentId`
- `baseModelPath`
- `adapterPath`
- `promptVersion`
- `generationConfigVersion`
- `contextBuilderVersion`
- `runnerKind`
- `serviceMode`

#### PersonaInferenceRequest
- `runtimeSignature`
- `messages`
- `generation`
- `traceMeta`

#### BuildPersonaContextOutput
- `messages`
- `stableTurnIds`
- `orphanTurnIds`
- `estimatedPromptTokens`
- `trimReport`

#### InferenceTrace 最小字段
- source type / source id
- runtime signature json
- final messages json
- generation config json
- estimated prompt tokens
- generated tokens
- latency fields
- trim report json
- output text / raw output json
- error / remote log path

---

## 3. 并行工作流

## Stream A：运行时与上下文层
**负责人：Subagent A**

范围：
- `packages/player/src/lib/personaRuntime.ts`
- `packages/player/src/lib/personaContextBuilder.ts`
- `packages/player/src/app/api/evals/live/sessions/[id]/chat/route.ts`
- `packages/player/src/app/api/evals/live/sessions/[id]/stream/route.ts`

目标：
- 抽出统一 runtime / generation / context builder
- 让 live chat / stream 不再手写 history 拼装逻辑

状态：`completed`

交付物：
- `packages/player/src/lib/personaRuntime.ts`
- `packages/player/src/lib/personaContextBuilder.ts`
- live chat/stream route 已接统一 runtime/context

---

## Stream B：H20 推理协议与 trace artifacts
**负责人：Subagent B**

范围：
- `scripts/evals/batch_chat_eval_qwen35_9b.py`
- `scripts/evals/live_chat_service_qwen35_9b.py`
- `packages/player/src/lib/remoteJobs.ts`
- 如有需要新增 `packages/player/src/lib/personaArtifacts.ts`

目标：
- online / offline 共用统一 request 概念
- batch 输出 per-case trace artifacts
- 整理日志/trace/export 路径约定

状态：`completed`

交付物：
- `packages/player/src/lib/personaArtifacts.ts`
- `packages/player/src/lib/remoteJobs.ts` trace artifact 路径与协议更新
- H20 batch/live 推理协议与 trace artifacts 已统一

---

## Stream C：评测规范与数据导出规范
**负责人：Subagent C**

范围：
- `docs/persona_eval_suite_spec_v1.md`
- `docs/persona_human_eval_rubric_v1.md`
- `docs/persona_data_export_spec_v1.md`

目标：
- 固化第一版 eval suite schema
- 固化人工评测 rubric
- 固化 SFT / preference 导出格式

状态：`completed`

交付物：
- `docs/persona_eval_suite_spec_v1.md`
- `docs/persona_human_eval_rubric_v1.md`
- `docs/persona_data_export_spec_v1.md`

---

## Stream D：Schema / Trace / Export 接入
**负责人：Mainline（等待 A/B/C 回流后整合）**

范围：
- `packages/player/prisma/schema.prisma`
- trace / export 相关 API 与 UI

说明：
- 这是中枢改动，先不拆给多个 agent，避免 schema 冲突
- 待 A/B 的接口实现方案稳定后统一整合

状态：`completed`

主线已完成：
- Prisma schema 增加 Prompt/Generation/Context profile、InferenceTrace、BadCase、TrainingExport
- live chat / stream 已将 trace 落库到 `InferenceTrace`
- Trace Viewer / Bad Case / Export API 与前端页面已接通
- offline run trace ingest 与 suite directory support 已接通

---

## 4. 第一批里程碑

### M1：运行时契约冻结
完成标志：
- `personaRuntime.ts` 存在
- `personaContextBuilder.ts` 存在
- live chat / stream 接入 context builder

### M2：推理协议可追溯
完成标志：
- H20 live / batch runner 可产出 request/trace artifacts
- 路径规范固定

### M3：评测口径冻结
完成标志：
- eval suite spec / rubric / export spec 三份文档完成

### M4：主线整合
完成标志：
- schema + trace 接入落地
- UI 可查看/导出基础结果

---

## 5. 当前状态

- M1：completed
- M2：completed
- M3：completed
- M4：completed


## 6. 第二批进展（已完成）

- Trace Viewer MVP 已上线：Run Detail 可下钻到 case 级 trace，支持查看 runtime signature / messages / generation / metrics / response / artifacts。
- Live chat / stream trace 已落库到 `InferenceTrace`。
- BadCase / Export API 已上线：
  - `GET/POST /api/evals/bad-cases`
  - `GET/POST /api/evals/exports`
- 导出文件落盘到 `artifacts/evals/exports/YYYYMMDD/`，包含 `jsonl + manifest.json + README.md`。

### 下一步建议
1. 补 bad case 标注前端入口（run detail / live session）
2. 补 export 列表与下载页
3. 补离线 suite 目录 loader（`suite.json + cases/*.jsonl`）
4. 将 offline case trace 逐步导入 `InferenceTrace` 数据表


## 7. 第三批进展（已完成）

- 已新增 bad case 标注前端入口：
  - run detail case 行可直接“标为 bad case”
  - live transcript 的 assistant turn 可直接“标坏例”
- 已新增 bad cases 列表页：`/admin/evals/bad-cases`
- 已新增 exports 列表页：`/admin/evals/exports`
- 已新增 export 下载接口：`/api/evals/exports/<id>/download`
- AdminNav 与 Eval Center 已补入口。

### 当前最短闭环
1. 在 run detail / live session 标坏例
2. 在 bad cases / exports 页面查看记录
3. 通过 export API 生成 JSONL
4. 从 exports 页面下载导出文件


## 8. 第四批进展（已完成）

- 已新增 offline trace ingest 闭环：
  - `POST /api/evals/runs/[id]/ingest-traces` 可把 batch run 的 case-level traces 导入 `InferenceTrace`
  - run detail 页面已新增一键 ingest 按钮，并展示 imported / updated / skipped / missingTraceArtifacts 统计
- 已补齐 suite directory support：
  - `POST /api/evals/suites` 现在支持 `suite.json + cases/*.jsonl` 目录形式的 case count 统计
  - 本地与远端 H20 均支持 case 数量探测
  - batch eval runner 已支持目录形式 suite 读取
- 已补齐 bad case 批量导出前端：
  - bad cases 页面支持勾选样本，直接生成 training export
  - exports 页面支持查看记录与下载 JSONL

### 当前 P0 MVP 闭环
1. 创建/维护 eval suite（支持单 JSONL 或 suite 目录）
2. 发起 offline run 或 live session
3. 在 run detail / trace viewer / live transcript 中定位坏例
4. 标 bad case，并批量导出为训练数据
5. 把 offline traces / live traces 统一沉淀到 `InferenceTrace` 做后续分析

### 下一步建议
1. 为 `POST /api/evals/suites` 与 export / ingest 路由补最小自动化测试
2. 在 Eval Center 首页补 bad case / export / trace 统计总览
3. 为 trace viewer 增加 diff / compare 入口，支撑 prompt / ckpt 对比


## 9. 第五批进展（已完成）

- 已补最小自动化测试基线：
  - `packages/player/vitest.config.ts`
  - `packages/player/package.json` 新增 `test` script
- 已新增 3 组 Persona Harness 相关 route tests：
  - `tests/api/evals/suites.route.test.ts`
  - `tests/api/evals/ingest-traces.route.test.ts`
  - `tests/api/evals/exports.route.test.ts`
- 当前已覆盖的关键闭环：
  - suite 目录 case count
  - offline trace ingest force update
  - training export happy path

### 已验证
- `cd packages/player && pnpm test`
- `cd packages/player && pnpm exec tsc --noEmit --pretty false`
- `cd packages/player && pnpm exec eslint 'tests/api/evals/*.test.ts' 'vitest.config.ts'`


## 10. 第六批进展（已完成）

- 已升级 Eval Center 首页总览：`/admin/evals`
- 新增 dashboard 聚合层：`packages/player/src/lib/evalDashboard.ts`
- 首页现在可直接查看：
  - Offline Eval Health（run 状态分布）
  - Live Infer Health（session / service 状态）
  - Trace Coverage（offline / live / error trace）
  - Data Flywheel（bad case / export / export items）
- 已补最近活动面板：
  - recent eval runs
  - recent bad cases
  - recent exports

### 已验证
- `cd packages/player && pnpm exec tsc --noEmit --pretty false`
- `cd packages/player && pnpm exec eslint 'src/app/admin/evals/page.tsx' 'src/lib/evalDashboard.ts' 'src/lib/evalAdmin.ts'`
- `cd packages/player && pnpm test`


## 11. 仓库结构重构（进行中 / 已落地第一步）

- 已将仓库边界重构为：
  - `packages/player`：前端 / 控制台 / API route / Prisma
  - `packages/agent`：persona harness / llm runner / H20 orchestration / trace/export domain logic
- 旧的根目录 `player` 兼容入口已移除，统一使用 `packages/player`
- 根目录 `scripts/evals/` 仍作为脚本兼容目录保留
- 后续约束：
  - 新的 harness / runner / llm 相关实现统一进入 `packages/agent`
  - `packages/player` 只保留前端与 web control plane 相关代码
