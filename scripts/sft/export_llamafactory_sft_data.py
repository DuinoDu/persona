#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SYSTEM_ANCHOR_V1 = """你需要模拟一位判断力强、现实主义、结果导向的女性咨询者，你叫曲曲。

回答时遵守以下稳定行为规则：

1. 先判断用户的问题前提是否成立；如果前提错了，先纠偏，不顺着错误前提继续聊。
2. 如果用户表达模糊、发散、一次问很多问题，先收束问题；优先让对方讲清事实、背景、基本盘、关键冲突，再回答。
3. 优先处理“本质问题”，而不是表面情绪；经常把问题拆成事实、资源、人性/需求、长期结果几个层面来看。
4. 回答顺序通常是：先给判断或结论，再解释原因，再给执行建议或推进路径。
5. 风格直接、克制、口语化，但不要故意堆口头禅；允许适度反问、纠偏、打断，但不要无意义攻击。
6. 不做廉价鼓励，不做空泛安慰，不用“你很好你值得”式模板话；不要为了安抚用户而牺牲判断。
7. 不做道德说教，重点看人性、需求、利益结构、现实约束、成本收益、筹码位置和长期稳定性。
8. 对明显的幻想、自我欺骗、低价值纠缠、沉没成本和讨好型行为，要直接指出，并把话题拉回更有效的选择。
9. 如果一个选项明显更优，不要假装平衡地两边都说；应明确给出倾向性判断。
10. 在多轮对话中保持立场、框架和价值判断一致，不要前后摇摆。

总目标：
- 先帮用户把问题看清楚，
- 再帮用户找到最关键的矛盾，
- 最后给出更现实、更可执行的判断与动作。"""


def stable_bucket(key: str, seed: int) -> float:
    digest = hashlib.sha1(f"{seed}:{key}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(16**12)


def choose_split(episode_id: str, conversation_id: str, seed: int, dev_ratio: float) -> str:
    key = episode_id or conversation_id
    return "dev" if stable_bucket(key, seed) < dev_ratio else "train"


def merge_turns(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    role_map = {"user": "user", "persona": "assistant", "assistant": "assistant"}
    for turn in turns:
        role = role_map.get(turn.get("role"))
        text = (turn.get("text") or "").strip()
        if not role or not text:
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n\n" + text
        else:
            messages.append({"role": role, "content": text})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    while messages and messages[-1]["role"] != "assistant":
        messages.pop()
    if not messages:
        return []
    return messages


def build_conversation_messages(turns: list[dict[str, str]], system_anchor: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system_anchor}] + turns


def build_turn_samples(turns: list[dict[str, str]], system_anchor: str) -> list[list[dict[str, str]]]:
    samples: list[list[dict[str, str]]] = []
    for idx, message in enumerate(turns):
        if message["role"] != "assistant":
            continue
        if idx == 0 or turns[idx - 1]["role"] != "user":
            continue
        sample = [{"role": "system", "content": system_anchor}] + turns[: idx + 1]
        samples.append(sample)
    return samples


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export persona annotations to LLaMA-Factory datasets.")
    parser.add_argument("--conversation-input", default="data/05_annotations/sft_v1/conversation_v1.jsonl")
    parser.add_argument("--output-dir", default="artifacts/llamafactory_data")
    parser.add_argument("--seed", type=int, default=20260327)
    parser.add_argument("--dev-ratio", type=float, default=0.05)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    conversation_path = (repo_root / args.conversation_input).resolve()
    output_dir = (repo_root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    anchor_path = output_dir / "system_anchor_v1.txt"
    anchor_path.write_text(SYSTEM_ANCHOR_V1 + "\n", encoding="utf-8")

    conv_rows = {"train": [], "dev": []}
    turn_rows = {"train": [], "dev": []}
    split_manifest: list[dict[str, Any]] = []
    stats = {
        "conversation_records_seen": 0,
        "conversation_records_exported": 0,
        "turn_samples_exported": 0,
        "splits": {"train": {"conversation": 0, "turn": 0}, "dev": {"conversation": 0, "turn": 0}},
    }

    with conversation_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            stats["conversation_records_seen"] += 1
            turns = merge_turns(obj.get("turns") or [])
            if len(turns) < 2 or not any(t["role"] == "assistant" for t in turns):
                continue
            source = obj.get("source") or {}
            episode_id = str(source.get("episode_id") or "")
            conversation_id = str(obj.get("conversation_id") or "")
            split = choose_split(episode_id, conversation_id, args.seed, args.dev_ratio)
            conv_rows[split].append({
                "messages": build_conversation_messages(turns, SYSTEM_ANCHOR_V1),
                "conversation_id": conversation_id,
                "episode_id": episode_id,
                "source_section_file": source.get("section_file"),
            })
            stats["conversation_records_exported"] += 1
            stats["splits"][split]["conversation"] += 1

            turn_samples = build_turn_samples(turns, SYSTEM_ANCHOR_V1)
            for sample_idx, sample in enumerate(turn_samples):
                turn_rows[split].append({
                    "messages": sample,
                    "conversation_id": conversation_id,
                    "episode_id": episode_id,
                    "turn_sample_id": f"{conversation_id}__{sample_idx:04d}",
                    "source_section_file": source.get("section_file"),
                })
            stats["turn_samples_exported"] += len(turn_samples)
            stats["splits"][split]["turn"] += len(turn_samples)
            split_manifest.append({
                "conversation_id": conversation_id,
                "episode_id": episode_id,
                "split": split,
                "assistant_turn_samples": len(turn_samples),
            })

    write_jsonl(output_dir / "ququ_conversation_v1_train.jsonl", conv_rows["train"])
    write_jsonl(output_dir / "ququ_conversation_v1_dev.jsonl", conv_rows["dev"])
    write_jsonl(output_dir / "ququ_turn_sft_v1_train.jsonl", turn_rows["train"])
    write_jsonl(output_dir / "ququ_turn_sft_v1_dev.jsonl", turn_rows["dev"])

    tags = {
        "role_tag": "role",
        "content_tag": "content",
        "user_tag": "user",
        "assistant_tag": "assistant",
        "system_tag": "system",
    }
    dataset_info = {
        "ququ_conversation_v1_train": {
            "file_name": "ququ_conversation_v1_train.jsonl",
            "formatting": "sharegpt",
            "columns": {"messages": "messages"},
            "tags": tags,
        },
        "ququ_conversation_v1_dev": {
            "file_name": "ququ_conversation_v1_dev.jsonl",
            "formatting": "sharegpt",
            "columns": {"messages": "messages"},
            "tags": tags,
        },
        "ququ_turn_sft_v1_train": {
            "file_name": "ququ_turn_sft_v1_train.jsonl",
            "formatting": "sharegpt",
            "columns": {"messages": "messages"},
            "tags": tags,
        },
        "ququ_turn_sft_v1_dev": {
            "file_name": "ququ_turn_sft_v1_dev.jsonl",
            "formatting": "sharegpt",
            "columns": {"messages": "messages"},
            "tags": tags,
        },
    }
    (output_dir / "dataset_info.json").write_text(json.dumps(dataset_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "split_manifest_smoke.json").write_text(json.dumps(split_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "dataset_build_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"output_dir": str(output_dir), **stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
