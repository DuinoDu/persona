# RFC: 基于用户反馈的本地 AI 字幕自动修复

- 日期：2026-03-25
- 状态：MVP 已开始实现
- 目标：用户提交字幕反馈后，系统自动创建本地 AI 修复任务；AI 产出结构化修复建议；满足阈值时直接 in-place 修复原字幕 JSON；后台可看到状态，前端刷新后看到最新字幕。

## 1. 背景

当前反馈功能已经能记录：
- 哪段音频
- 哪句字幕
- 用户反馈内容

但还不能自动修复，因为展示层字幕并不能稳定映射回原始字幕 JSON。要实现自动修复，必须在反馈中保存“原始字幕定位信息”，并引入后台 job + worker。

## 2. MVP 设计原则

1. **原文件 in-place 修复**：直接修改 Next API 正在读取的字幕 JSON。
2. **保留审计**：数据库保存反馈、AI 建议、状态、错误。
3. **低耦合调度**：API 只负责入队，不同步等待 AI；本地 worker 轮询 pending job。
4. **结构化输出**：AI 必须输出 JSON，便于自动校验和自动应用。
5. **保守自动应用**：仅在高置信、单句、最小编辑时自动应用，否则转人工。

## 3. 数据模型

### 3.1 Feedback

新增字段：
- `subtitleSourceKind`: `sentences` / `segments`
- `subtitleSourcePath`: 原始字幕 JSON 绝对路径
- `subtitleSourceIndex`: 原始数组下标
- `subtitleAbsStart` / `subtitleAbsEnd`: 原始绝对时间
- `repairStatus`: `pending` / `running` / `applied` / `needs_human` / `rejected` / `failed`
- `repairSummary`
- `repairConfidence`
- `repairedText`
- `repairError`
- `repairedAt`
- `updatedAt`

### 3.2 FeedbackRepairJob

职责：记录任务执行状态、输入输出、报错与重试信息。

关键字段：
- `feedbackId`
- `status`
- `attempt`
- `model`
- `promptVersion`
- `inputJson`
- `outputJson`
- `error`
- `startedAt` / `finishedAt`

## 4. 触发流程

```text
用户长按字幕反馈
  -> POST /api/feedback
  -> 写入 Feedback(repairStatus=pending)
  -> 写入 FeedbackRepairJob(status=pending)
  -> 本地 worker 轮询到 job
  -> 读取原始字幕 JSON + 上下文
  -> 调用本地 AI 任务
  -> 校验结构化输出
  -> 满足条件则 in-place 改字幕 JSON
  -> 更新 Feedback / FeedbackRepairJob 状态
  -> 前端刷新后看到新字幕
```

## 5. 为什么选择 in-place 修复

### 选型

本期采用：**直接修改 API 当前读取的原字幕 JSON 文件**。

### 原因

- 当前 `/api/subtitles/[filename]` 是按请求实时读文件。
- 修复后无需额外切换 corrected path。
- 前端刷新即可看到最新数据。
- 实现最简单。

### 风险控制

- 原子写入：`tmp -> rename`
- 自动修复仅在高置信时执行
- 数据库保留 AI 输出、状态和错误

## 6. 字幕定位规则

字幕 API 需要返回：

```json
{
  "start": 0,
  "end": 3.2,
  "text": "...",
  "role": "host",
  "sourceKind": "sentences",
  "sourcePath": "/abs/path/00_开场.json",
  "sourceIndex": 42,
  "absStart": 321.12,
  "absEnd": 324.32
}
```

前端提交反馈时把这些字段一并带回。

## 7. AI 任务输入

worker 组装输入 JSON：

```json
{
  "feedback": {
    "id": "fb_xxx",
    "message": "识别错误 锋链"
  },
  "audio": {
    "id": "003-item-01",
    "filename": "003_01_01_25岁常春藤硕士_连麦.mp3",
    "date": "2026年3月5日",
    "personTag": "25岁常春藤硕士_连麦"
  },
  "target": {
    "sourceKind": "sentences",
    "sourcePath": "/abs/path/01_xxx.json",
    "sourceIndex": 42,
    "currentText": "这次连麦...推锋链...",
    "displayText": "这次连麦...推锋链...",
    "absStart": 840.12,
    "absEnd": 847.33
  },
  "context": {
    "prev": ["上一句", "上二句"],
    "next": ["下一句", "下二句"]
  },
  "policy": {
    "minimalEditOnly": true,
    "allowRewriteWholeSentence": false,
    "autoApplyConfidenceThreshold": 0.9
  }
}
```

## 8. Prompt

### System Prompt

```text
你是一个字幕纠错代理。
你的任务是根据用户反馈、目标字幕和上下文，判断这条字幕是否需要修复。

规则：
1. 只修正明显的 ASR 识别错误、错别字、同音误识别。
2. 不要润色，不要改写风格，不要扩写。
3. 优先最小编辑。
4. 证据不足时返回 NEEDS_HUMAN。
5. 输出必须是 JSON。
```

### User Prompt 模板

```text
[用户反馈]
{{feedback.message}}

[目标字幕]
{{target.currentText}}

[目标字幕时间]
{{target.absStart}} - {{target.absEnd}}

[上文]
{{context.prev}}

[下文]
{{context.next}}

请判断是否应修复，并按 JSON schema 输出结果。
```

## 9. AI 输出

```json
{
  "decision": "APPLY",
  "confidence": 0.96,
  "summary": "将‘推锋链’修正为‘锋链’",
  "correctedText": "这次连麦呢主要想和曲曲聊一下请教一下自己对于自己和男友锋链如何维护好自己的权益"
}
```

或：

```json
{
  "decision": "NEEDS_HUMAN",
  "confidence": 0.42,
  "summary": "仅根据反馈无法确定具体改法",
  "correctedText": null
}
```

## 10. Worker

worker 默认使用本机 `codex exec` 执行非交互任务：

```bash
npm run feedback-worker
```

环境变量：
- `FEEDBACK_REPAIR_ENABLED=true`
- `FEEDBACK_REPAIR_POLL_MS=3000`
- `FEEDBACK_REPAIR_MODEL=` 可选
- `FEEDBACK_REPAIR_USE_OSS=false`
- `FEEDBACK_REPAIR_AUTO_APPLY_CONFIDENCE=0.9`
- `FEEDBACK_REPAIR_WORKDIR=.feedback-repair-work`
- `FEEDBACK_REPAIR_TRANSCRIBE_MODEL=glm-asr-2512`
- `FEEDBACK_REPAIR_AUDIO_CLIP_PAD_SECONDS=1.5`
- `FEEDBACK_REPAIR_JUDGE_BACKENDS=codex,traecli,aiden`
- `FEEDBACK_REPAIR_BIGMODEL_API_KEY=` 单独提供给 transcription
- `FEEDBACK_REPAIR_BIGMODEL_BASE_URL=` 可选，默认为 `https://open.bigmodel.cn/api/paas/v4`

## 10.1 音频证据链路

MVP 后续增强已加入：
- worker 会优先定位当前 clip 音频文件
- 使用 ffmpeg 按反馈字幕的相对时间切出 wav
- 若提供 `FEEDBACK_REPAIR_BIGMODEL_API_KEY`，会调用 BigModel `/audio/transcriptions` 获取音频转写
- 音频转写结果作为 `audioEvidence.transcription` 注入 AI prompt
- 若转写失败，不阻塞第一优先级的显式反馈修复；任务可继续走显式反馈或转人工

## 11. Next API 感知更新

为了让 Next API 直接读到更新结果：

1. 字幕接口使用 `dynamic = "force-dynamic"`
2. API 响应返回 `Cache-Control: no-store`
3. 前端拉字幕使用 `fetch(..., { cache: "no-store" })`

这样字幕 JSON 被原子写回后，下一次请求就能读到新内容。

## 12. 后台展示

反馈后台显示：
- `repairStatus`
- `repairConfidence`
- `repairSummary`
- `repairedText`
- `repairError`
- `repairedAt`

并且页面设为动态渲染，刷新即可看到最新状态。

## 13. MVP 范围

本次实现范围：
- 保存原始字幕定位信息
- 反馈自动入队
- 本地 worker 轮询执行
- AI 结构化输出
- 高置信 in-place 回写字幕文件
- 后台展示修复状态

暂不实现：
- 音频切片与二次 ASR
- 多句联合修复
- WebSocket 实时推送
- 人工审核工作流
