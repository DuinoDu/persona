# Eval Admin V1 Task List

## Goal
在现有 `player` 后台上增量实现一套评测工具，支持：
- 离线批量 infer
- 在线实时 infer 的服务编排入口
- 评测结果浏览、盲评与后续 insight 汇总

约束：
- 不替换现有 Player
- 所有模型执行通过 H20 完成
- 长时间任务必须通过 `tmux` 启动

## Phase 0: Foundation
- [x] 明确总体架构：`player` 作为控制面，H20 作为执行面
- [x] 复盘当前训练/单条推理的运行范式：shell runner + python + tmux + log/status/output
- [x] 落地 Prisma 数据模型
- [x] 增加评测后台导航和总览页

## Phase 1: Admin Data Model
- [x] `InferHost`
  - 存推理 H20 的 SSH 信息、workspace、GPU 调度策略
- [x] `ModelDeployment`
  - 存 base model、adapter、runner、在线服务信息
- [x] `EvalSuite`
  - 存固定评测集元数据和源文件路径
- [x] `EvalRun`
  - 存离线批量评测任务、tmux session、log/status/output 路径、结果摘要
- [x] `LiveSession`
  - 存在线连麦会话元数据
- [x] `LiveTurn`
  - 存多轮实时对话 transcript

## Phase 2: Offline Batch Eval
- [x] 新增批量推理脚本：一次加载模型，跑完整个 suite
- [x] 新增 shell runner：复用当前 py312 环境与 cache 约定
- [x] 评测 run 创建 API
- [x] 通过 SSH 到 infer H20 启动远程 `tmux` job
- [x] run 详情页支持刷新远程状态与 summary
- [x] 输出基础健康指标：blank / short / control-token / avg length / avg tokens

## Phase 3: Online Live Infer
- [x] 增加 live 页面入口
- [x] 部署在线 infer service 的元数据模型
- [x] 支持记录 live session / live turns
- [ ] 接入实时接口（SSE 或 WebSocket）
- [x] 支持模拟连麦场景的多轮对话（当前为请求响应版）
- [x] 支持在后台展示 service session/log/status/exit code/health 诊断信息

## Phase 4: Human Eval / Arena
- [x] Arena 页面：A/B 盲评
- [x] 评分维度：persona / judgment / premise / structure / actionability / naturalness / stability
- [x] 失败标签：too_short / style_drift / no_premise_fix / vague_comfort / too_harsh / multi_turn_drift / leakage
- [x] case 详情页展示多模型输出对比（当前通过 Arena case 详情视图承载）

## Phase 5: Insight Loop
- [ ] slice 聚合统计
- [ ] 最差样本集合
- [ ] 最佳样本集合
- [ ] 自动生成下一轮训练建议

## This Turn Scope
- [x] 产出 task list
- [x] 增加 Prisma schema 和后台页面骨架
- [x] 增加 offline batch eval runner
- [x] 增加 run 创建 API 与远程 tmux 启动骨架
- [x] 验证不影响现有 Player

## Current Blocker
- [ ] GPU live infer 仍被底层 `model.generate` 的 `Floating-point exception (exit 136)` 阻塞
  - 现状：service `/health` 正常，首条 `/chat` 会在 Qwen3.5 prefill 路径崩溃
  - 已验证无效的绕法：`use_cache=False`、改为单线程 `HTTPServer`
  - 当前可用结论：控制面、服务编排、session/chat API、前端 live console 已落地；GPU 在线生成仍需进一步替换推理栈或继续定位底层 runtime 问题
