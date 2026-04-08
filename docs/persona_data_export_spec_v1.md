# Persona Data Export Spec v1

## 1. 目标

本文定义曲曲项目 P0 阶段的 bad case 导出格式。导出目标不是“做报表”，而是把评测中发现的问题直接转成下一轮训练可消费的数据。

本规范支持两种最重要的导出：
- `SFT candidate`
- `preference pair candidate`

---

## 2. 基本原则

1. 导出必须保留原始上下文。
2. 导出必须带上 source metadata，能追溯到具体 run / session / case。
3. 导出必须区分“模型原始输出”和“人工改写目标”。
4. 导出必须和 annotation version 对齐。
5. 一条导出记录必须能直接喂给后续训练脚本，不依赖人脑补字段。

---

## 3. 导出目录

建议统一落盘到：

```text
artifacts/evals/exports/
  YYYYMMDD/
    export_<export_id>.jsonl
    manifest.json
    README.md
```

### 3.1 `manifest.json`

用于说明本次导出的范围和来源：

```json
{
  "export_id": "export_20260407_001",
  "version": "export_v1",
  "created_at": "2026-04-07T00:00:00Z",
  "source_types": ["offline_case", "live_turn", "arena_pair"],
  "record_count": 0,
  "record_types": ["sft_candidate", "preference_pair_candidate"]
}
```

---

## 4. SFT Candidate Format

### 4.1 适用场景

当问题是：
- 模型答偏了
- 模型太空
- 模型不够像
- 模型忘记上下文

并且人工可以写出更好的目标回复时，导出 SFT candidate。

### 4.2 推荐 schema

```json
{
  "record_type": "sft_candidate",
  "version": "export_v1",
  "candidate_id": "sft_001",
  "source": {
    "source_type": "offline_case",
    "source_id": "ququ_persona_v1_call_long_0012",
    "project": "ququ_youtube",
    "annotation_version": "annotation_v1",
    "model_id": "string",
    "deployment_id": "string",
    "run_id": "string",
    "live_session_id": "string | null",
    "turn_id": "string | null",
    "case_id": "string | null",
    "slice": "call_long",
    "prompt_version": "string",
    "context_builder_version": "string",
    "generation_config_version": "string"
  },
  "input_messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "model_output": "string",
  "edited_target": "string",
  "labels": {
    "failure_tags": ["style_drift"],
    "topic_primary": "career",
    "difficulty": "medium",
    "reply_type": "advice"
  },
  "metadata": {
    "source_path": "string",
    "trace_path": "string",
    "prompt_tokens": 0,
    "generated_tokens": 0,
    "latency_ms": 0,
    "annotator_id": "string",
    "reviewer_id": "string | null",
    "created_at": "date-time"
  }
}
```

### 4.3 字段要求

- `input_messages` 必须是最终喂给模型的完整上下文。
- `model_output` 必须是原始模型输出，不得覆盖。
- `edited_target` 是人工修正后的训练目标。
- `edited_target` 不能与 `model_output` 完全相同，除非是确认正确样本。
- `labels.failure_tags` 建议至少 1 个。

---

## 5. Preference Pair Candidate Format

### 5.1 适用场景

当同一上下文下有两个候选回复，需要表达“哪个更像曲曲、更自然、更稳”时，导出 preference pair candidate。

### 5.2 推荐 schema

```json
{
  "record_type": "preference_pair_candidate",
  "version": "export_v1",
  "pair_id": "pair_001",
  "source": {
    "source_type": "arena_pair",
    "source_id": "arena_20260407_001",
    "project": "ququ_youtube",
    "annotation_version": "annotation_v1",
    "model_id": "string",
    "deployment_id": "string",
    "run_id": "string",
    "live_session_id": "string | null",
    "turn_id": "string | null",
    "case_id": "string | null",
    "slice": "adversarial",
    "prompt_version": "string",
    "context_builder_version": "string",
    "generation_config_version": "string"
  },
  "context_messages": [
    {"role": "user", "content": "..."}
  ],
  "chosen": {
    "candidate_id": "cand_a",
    "provenance": "human",
    "text": "string"
  },
  "rejected": {
    "candidate_id": "cand_b",
    "provenance": "sft_model",
    "text": "string"
  },
  "judgement": {
    "winner": "chosen",
    "preference_strength": "medium",
    "reason_tags": [
      "more_like_persona",
      "better_value_alignment",
      "less_ooc"
    ],
    "scores": {
      "style_similarity_winner": "chosen",
      "structure_similarity_winner": "chosen",
      "value_alignment_winner": "chosen",
      "naturalness_winner": "chosen",
      "intent_hit_winner": "chosen"
    }
  },
  "metadata": {
    "source_path": "string",
    "trace_path": "string",
    "annotator_id": "string",
    "reviewer_id": "string | null",
    "created_at": "date-time"
  }
}
```

### 5.3 `winner` 规则

- `chosen`：人工选定的更优回复
- `rejected`：较差回复
- 如果两边都差，仍可以导出，但要写明 `preference_strength=weak` 并补充 notes

---

## 6. 来源类型

导出至少支持 3 类来源：

1. `offline_case`
2. `live_turn`
3. `arena_pair`

### 6.1 `offline_case`

来源于离线 batch eval case，适合批量发现系统性问题。

### 6.2 `live_turn`

来源于在线连麦会话，适合抓真实用户场景坏例。

### 6.3 `arena_pair`

来源于 A/B 盲评，适合生成 preference pair。

---

## 7. 导出流程

### 7.1 SFT candidate 导出流程

1. 选中 bad case。
2. 读取原始上下文。
3. 保存原始输出。
4. 人工编辑出 `edited_target`。
5. 补 failure tags。
6. 写出一条 JSONL。

### 7.2 Preference pair 导出流程

1. 选中同一上下文的两个候选。
2. 盲评后确定 `chosen` / `rejected`。
3. 补 reason tags。
4. 填 preference strength。
5. 写出一条 JSONL。

---

## 8. QC 规则

以下情况视为导出失败：

1. `input_messages` 为空。
2. `chosen.text` 与 `rejected.text` 完全相同。
3. `edited_target` 为空。
4. `source_id` 无法追溯。
5. 缺少 `prompt_version` 或 `context_builder_version`。
6. `record_type` 与导出目标不一致。

---

## 9. 工程落地建议

建议工程侧实现以下三层：

1. `personaExport.ts`：统一构造导出对象。
2. `export` API：从 run / live / arena 直接导出。
3. `download` UI：把导出文件下载给训练脚本。

---

## 10. 验收标准

满足以下条件即认为导出规范可用：

1. 一条 bad case 可以导出成 SFT candidate。
2. 一条 A/B 评测可以导出成 preference pair candidate。
3. 导出记录能追溯到原始 run / session / case。
4. 导出 JSONL 可直接被训练脚本消费。
5. 导出文件和 manifest 能一并落盘归档。

