import type { PersonaTurn } from "./personaContextBuilder";
import {
  buildPersonaMemoryMessages,
  recallPersonaMemory,
  type PersonaMemoryRecall,
  type PersonaMemoryState,
} from "./personaMemory";
import type { PersonaMessage } from "./personaRuntime";

export interface PersonaToolPlan {
  tools: string[];
  reasons: string[];
}

export interface PersonaToolLoopResult {
  plan: PersonaToolPlan;
  recall: PersonaMemoryRecall;
  messages: PersonaMessage[];
}

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function isGreeting(text: string) {
  const normalized = text.replace(/\s+/g, "");
  return ["你好", "hi", "hello", "在吗", "早上好", "晚上好"].some((token) =>
    normalized.toLowerCase().includes(token)
  );
}

function needsRecall(text: string) {
  return ["之前", "刚才", "上次", "前面", "记得", "还记得", "总结", "背景", "情况"].some((token) =>
    text.includes(token)
  );
}

function needsPlanning(text: string) {
  return ["怎么", "怎么办", "如何", "下一步", "计划", "推进", "建议", "选择", "决策"].some((token) =>
    text.includes(token)
  );
}

function summarizeRecentTurns(turns: PersonaTurn[]) {
  return turns.slice(-4).map((turn) => `${turn.role}:${asString(turn.content).slice(0, 80)}`).join(" | ");
}

export function planPersonaToolLoop(input: {
  query: string;
  memoryState: PersonaMemoryState;
  turns?: PersonaTurn[];
}) {
  const query = asString(input.query);
  const tools: string[] = [];
  const reasons: string[] = [];
  const hasProfile = input.memoryState.profile.length > 0;
  const hasOpenLoops = input.memoryState.openLoops.length > 0;
  const hasRecallableMemory = input.memoryState.facts.length > 0 || input.memoryState.episodes.length > 0;
  const recall = needsRecall(query);
  const planning = needsPlanning(query);

  if (hasProfile && !isGreeting(query)) {
    tools.push("profile_snapshot");
    reasons.push("profile_memory_available");
  }
  if (hasOpenLoops && (planning || recall || query.length >= 8)) {
    tools.push("open_loops");
    reasons.push("open_loops_relevant");
  }
  if (hasRecallableMemory && (planning || recall || query.length >= 12)) {
    tools.push("memory_search");
    reasons.push("memory_search_relevant");
  }
  if (input.turns && input.turns.length >= 8 && tools.includes("memory_search") === false && hasRecallableMemory) {
    tools.push("memory_search");
    reasons.push("long_session_recall_guard");
  }
  if (input.turns && input.turns.length > 0) {
    const recent = summarizeRecentTurns(input.turns);
    if (recent.length > 0) {
      reasons.push(`recent_turns=${recent}`);
    }
  }

  return {
    tools: Array.from(new Set(tools)).slice(0, 3),
    reasons,
  } satisfies PersonaToolPlan;
}

export function runPersonaToolLoop(input: {
  query: string;
  memoryState: PersonaMemoryState;
  turns?: PersonaTurn[];
}) {
  const plan = planPersonaToolLoop(input);
  const recall = recallPersonaMemory({
    state: input.memoryState,
    query: input.query,
    includeProfile: plan.tools.includes("profile_snapshot"),
    topFacts: plan.tools.includes("memory_search") ? 4 : 0,
    topEpisodes: plan.tools.includes("memory_search") ? 2 : 0,
    topOpenLoops: plan.tools.includes("open_loops") ? 3 : 0,
  });
  const messages = buildPersonaMemoryMessages({
    recall,
    toolNames: plan.tools,
  });

  return {
    plan,
    recall,
    messages,
  } satisfies PersonaToolLoopResult;
}
