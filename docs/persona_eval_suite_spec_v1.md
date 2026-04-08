# Persona Eval Suite Spec v1

## 1. 目标

本文定义曲曲项目第一版离线评测集 `eval suite` 的目录规范、数据结构、字段口径和最小验收规则，供工程侧直接实现批量 infer、结果聚合和回归评测。

本规范面向的不是通用 benchmark，而是曲曲 persona 的多轮咨询场景。核心要求是：
- 输入可复现
- 评测 slice 清晰
- 多轮上下文保真
- 结果可按 case 下钻

---

## 2. 目录规范

建议评测集统一放在：

```text
data/evals/suites/
  ququ_persona_v1/
    suite.json
    cases/
      opening.jsonl
      call_short.jsonl
      call_long.jsonl
      comment.jsonl
      adversarial.jsonl
      followup.jsonl
      memory_consistency.jsonl
    README.md
```

### 2.1 文件职责

- `suite.json`：suite 元信息，控制版本、入口、统计信息、默认评测参数。
- `cases/*.jsonl`：具体 case 数据，一行一个 case。
- `README.md`：人工阅读说明，描述这个 suite 主要覆盖哪些 persona 行为。

---

## 3. Suite 元信息

`suite.json` 建议字段如下：

```json
{
  "suite_id": "ququ_persona_v1",
  "version": "eval_suite_v1",
  "title": "QuQu Persona Eval Suite v1",
  "description": "Offline eval suite for QuQu persona multi-turn behavior.",
  "status": "active",
  "language": "zh",
  "persona_name": "曲曲",
  "default_model_family": "qwen",
  "default_max_new_tokens": 256,
  "default_temperature": 0.7,
  "default_top_p": 0.95,
  "source": {
    "project": "ququ_youtube",
    "annotation_version": "annotation_v1"
  },
  "slices": [
    "opening",
    "call_short",
    "call_long",
    "comment",
    "adversarial",
    "followup",
    "memory_consistency"
  ],
  "stats": {
    "case_count": 0,
    "estimated_turn_count": 0
  }
}
```

### 3.1 字段口径

- `suite_id`：全局唯一，建议稳定命名，不随模型变化。
- `version`：suite 规范版本，不等于模型版本。
- `status`：`active | frozen | archived`。
- `default_model_family`：用于提示评测系统默认底座，不绑定具体 checkpoint。
- `slices`：该 suite 覆盖的 case 分片类型。
- `stats`：由构建脚本生成，人工不改。

---

## 4. Case Schema

每个 case 建议与现有 `docs/annotation_v1/schemas/benchmark_record.schema.json` 保持兼容，并在评测场景下补充更明确的 `eval` 元数据。

### 4.1 推荐 case 文件结构

每行一个对象，字段建议如下：

```json
{
  "record_type": "benchmark_case",
  "version": "annotation_v1",
  "benchmark_id": "ququ_persona_v1_opening_0001",
  "category": "normal_qa",
  "slice": "opening",
  "messages": [
    {"turn_index": 0, "role": "user", "text": "..." },
    {"turn_index": 1, "role": "persona", "text": "..." }
  ],
  "expected": {
    "target_reply_types": ["direct_answer"],
    "target_style_tones": ["direct", "restrained"],
    "target_structure_patterns": ["conclusion_first"],
    "target_reasoning_patterns": ["goal_alignment_check"],
    "target_value_signals": ["realism", "result_oriented"],
    "required_interaction_policies": {
      "asks_clarifying_question_first": false,
      "corrects_premise_first": false,
      "reduces_complexity_first": true,
      "refuses_invalid_premise": false,
      "comforts_emotion_explicitly": false,
      "reframes_problem": true
    },
    "must_not_have": ["template_language", "generic_comfort"],
    "max_ooc_risk": "low",
    "reference_answer": "可选",
    "rubric_notes": "可选"
  },
  "meta": {
    "topic_primary": "career",
    "topic_secondary": ["money"],
    "difficulty": "medium",
    "safety_flags": [],
    "estimated_input_tokens": 1200,
    "estimated_output_tokens": 256
  },
  "audit": {
    "annotation_status": "frozen",
    "annotator_id": "system",
    "created_at": "2026-04-07T00:00:00Z"
  }
}
```

### 4.2 必须字段

case 至少要包含：
- `benchmark_id`
- `category`
- `slice`
- `messages`
- `expected.target_reply_types`
- `expected.max_ooc_risk`
- `meta.topic_primary`
- `audit.annotation_status`

---

## 5. Slice 定义

### 5.1 `opening`

用于评估开场定调能力。

看点：
- 是否快速进入 persona 状态
- 是否在开场就有判断框架
- 是否避免空泛寒暄

### 5.2 `call_short`

短多轮咨询，通常 3 到 6 轮。

看点：
- 能否在短上下文里抓到核心问题
- 是否有明确建议

### 5.3 `call_long`

长多轮咨询，通常 8 轮以上。

看点：
- 是否记住前文
- 是否前后一致
- 是否会越聊越空

### 5.4 `comment`

用于短评论式回复。

看点：
- 是否短而有力
- 是否保持角色
- 是否避免模板化

### 5.5 `adversarial`

诱导模型说出不该说的话，或给出明显错误前提。

看点：
- 是否纠偏
- 是否拒绝错误前提
- 是否出戏

### 5.6 `followup`

用户追问一轮或多轮。

看点：
- 是否延续前一轮判断
- 是否补足此前漏掉的信息

### 5.7 `memory_consistency`

用于检查历史事实保持一致。

看点：
- 是否忘记上下文
- 是否前后冲突

---

## 6. 评测输出要求

每次 batch eval 至少要输出：
- `run_id`
- `suite_id`
- `deployment_id`
- `model_snapshot`
- `case_id`
- `slice`
- `messages`
- `generated_text`
- `prompt_tokens`
- `generated_tokens`
- `latency_ms`
- `trace_path`
- `judge_summary`（如果有）

建议评测结果按以下层次聚合：
- suite 级
- slice 级
- case 级

---

## 7. 目录与命名约定

- suite 目录名建议使用稳定 slug，例如 `ququ_persona_v1`
- case_id 建议包含 suite、slice、序号，例如 `ququ_persona_v1_call_long_0012`
- 新版本 suite 必须新建目录，不要覆盖旧目录

---

## 8. 验收标准

以下条件同时满足即视为 suite 规范可用：

1. 工程可以仅凭 `suite.json` 识别这个 suite 的版本、默认参数和 slice 列表。
2. 每个 case 都能被稳定加载成 `messages + expected + meta`。
3. 同一 case 可用于 offline batch infer、arena 对比和回归测试。
4. case 结果可按 `slice` 聚合统计。
5. case 文件与 schema 兼容，后续可直接接入数据库或 JSONL loader。

