import { createHash } from "node:crypto";
import type { PersonaMessage } from "./personaRuntime";

export const PERSONA_MEMORY_VERSION = "persona_memory_v1";

export interface PersonaProfileMemory {
  id: string;
  kind: "profile";
  key: string;
  value: string;
  keywords: string[];
  updatedAt: string;
  sourceTurnIds: string[];
}

export interface PersonaFactMemory {
  id: string;
  kind: "fact";
  text: string;
  keywords: string[];
  updatedAt: string;
  sourceTurnIds: string[];
}

export interface PersonaOpenLoopMemory {
  id: string;
  kind: "open_loop";
  text: string;
  keywords: string[];
  updatedAt: string;
  sourceTurnIds: string[];
}

export interface PersonaEpisodeMemory {
  id: string;
  kind: "episode";
  title: string;
  text: string;
  keywords: string[];
  updatedAt: string;
  sourceTurnIds: string[];
}

export interface PersonaMemoryState {
  version: string;
  profile: PersonaProfileMemory[];
  facts: PersonaFactMemory[];
  openLoops: PersonaOpenLoopMemory[];
  episodes: PersonaEpisodeMemory[];
}

export interface PersonaMemoryRecall {
  profile: PersonaProfileMemory[];
  facts: PersonaFactMemory[];
  openLoops: PersonaOpenLoopMemory[];
  episodes: PersonaEpisodeMemory[];
}

function asRecord(value: unknown) {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeText(value: string, maxLength = 160) {
  return value.replace(/\s+/g, " ").trim().slice(0, maxLength);
}

function normalizeKey(value: string) {
  return value.replace(/\s+/g, "").trim().toLowerCase();
}

function toIsoString(value?: string | Date | null) {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (value instanceof Date) {
    return value.toISOString();
  }
  return new Date().toISOString();
}

function stableId(seed: string) {
  return createHash("sha1").update(seed).digest("hex").slice(0, 16);
}

function uniqueStrings(values: string[]) {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function tokenize(text: string) {
  const normalized = normalizeText(text, 400).toLowerCase();
  const latin = normalized.match(/[a-z0-9]{2,}/g) ?? [];
  const cjk: string[] = Array.from(normalized).filter((char) => /[\u4e00-\u9fff]/.test(char));
  return uniqueStrings([...latin, ...cjk]);
}

function overlapScore(queryTokens: string[], itemTokens: string[], updatedAt: string) {
  const overlap = itemTokens.filter((token) => queryTokens.includes(token)).length;
  const numericOverlap = itemTokens.filter((token) => /^\d+$/.test(token) && queryTokens.includes(token)).length;
  const ageMs = Math.max(0, Date.now() - new Date(updatedAt).getTime());
  const recencyBonus = ageMs > 0 ? Math.max(0, 1 - ageMs / (1000 * 60 * 60 * 24 * 14)) : 1;
  return overlap * 2 + numericOverlap * 3 + recencyBonus;
}

function trimList<T>(items: T[], limit: number) {
  return items.slice(0, limit);
}

function mergeByKey<T extends { id: string; updatedAt: string }>(
  items: T[],
  keyOf: (item: T) => string,
  limit: number
) {
  const map = new Map<string, T>();
  for (const item of items) {
    const key = keyOf(item);
    const existing = map.get(key);
    if (!existing || new Date(item.updatedAt).getTime() >= new Date(existing.updatedAt).getTime()) {
      map.set(key, item);
    }
  }
  return Array.from(map.values()).sort((left, right) => right.updatedAt.localeCompare(left.updatedAt)).slice(0, limit);
}

function extractCity(text: string) {
  const cities = [
    "北京",
    "上海",
    "深圳",
    "广州",
    "杭州",
    "成都",
    "重庆",
    "苏州",
    "武汉",
    "西安",
    "南京",
    "天津",
    "长沙",
    "郑州",
    "厦门",
    "青岛",
    "香港",
  ];
  return cities.find((city) => text.includes(city)) || "";
}

function extractOccupation(text: string) {
  const labels = [
    "程序员",
    "工程师",
    "产品经理",
    "老师",
    "医生",
    "博士",
    "研究生",
    "硕士",
    "销售",
    "创业",
    "创业者",
    "主播",
    "电商",
    "咨询",
    "金融",
    "体制内",
    "国企",
    "自媒体",
    "带货",
    "宝妈",
  ];
  return labels.find((label) => text.includes(label)) || "";
}

function extractIncome(text: string) {
  const match = text.match(/(?:年薪|月薪|月入|收入|赚了)\s*([^，。；\s]{1,18})/);
  return match?.[0] || "";
}

function extractRelationshipState(text: string) {
  const labels = ["单身", "已婚", "离异", "恋爱", "订婚", "结婚", "二胎", "婚恋"];
  return labels.find((label) => text.includes(label)) || "";
}

function extractGoal(text: string) {
  const labels = [
    "婚恋",
    "脱单",
    "结婚",
    "相亲",
    "变现",
    "副业",
    "创业",
    "择城",
    "转型",
    "带货",
    "内容变现",
  ];
  return labels.find((label) => text.includes(label)) || "";
}

function extractProfileMemories(text: string, sourceTurnIds: string[], updatedAt: string) {
  const profile: PersonaProfileMemory[] = [];
  const age = text.match(/(\d{1,2})岁/)?.[0] || "";
  const city = extractCity(text);
  const occupation = extractOccupation(text);
  const income = extractIncome(text);
  const relationship = extractRelationshipState(text);
  const goal = extractGoal(text);

  const pairs = [
    ["年龄", age],
    ["城市", city],
    ["职业", occupation],
    ["收入", income],
    ["感情状态", relationship],
    ["核心诉求", goal],
  ] as const;

  for (const [key, value] of pairs) {
    const normalizedValue = normalizeText(value, 48);
    if (!normalizedValue) {
      continue;
    }
    profile.push({
      id: stableId(`profile:${key}:${normalizedValue}`),
      kind: "profile",
      key,
      value: normalizedValue,
      keywords: tokenize(`${key} ${normalizedValue}`),
      updatedAt,
      sourceTurnIds,
    });
  }

  return profile;
}

function splitSentences(text: string) {
  return text
    .split(/[。！？!?；;\n]/g)
    .map((item) => normalizeText(item, 96))
    .filter(Boolean);
}

function extractFactMemories(text: string, sourceTurnIds: string[], updatedAt: string) {
  const keywords = ["婚恋", "结婚", "脱单", "副业", "创业", "择城", "相亲", "关系", "收入", "年薪", "月入", "带货"];
  return splitSentences(text)
    .filter((sentence) => /\d/.test(sentence) || keywords.some((keyword) => sentence.includes(keyword)))
    .slice(0, 4)
    .map((sentence) => ({
      id: stableId(`fact:${sentence}`),
      kind: "fact" as const,
      text: sentence,
      keywords: tokenize(sentence),
      updatedAt,
      sourceTurnIds,
    }));
}

function extractOpenLoopMemories(text: string, sourceTurnIds: string[], updatedAt: string) {
  const triggers = ["怎么", "怎么办", "如何", "要不要", "能不能", "是否", "下一步", "计划", "推进"];
  return splitSentences(text)
    .filter((sentence) => sentence.includes("?") || sentence.includes("？") || triggers.some((item) => sentence.includes(item)))
    .slice(0, 3)
    .map((sentence) => ({
      id: stableId(`open_loop:${sentence}`),
      kind: "open_loop" as const,
      text: sentence,
      keywords: tokenize(sentence),
      updatedAt,
      sourceTurnIds,
    }));
}

function extractEpisodeMemories(
  userText: string,
  assistantText: string,
  sourceTurnIds: string[],
  updatedAt: string
) {
  const userSummary = normalizeText(userText, 72);
  const assistantSummary = normalizeText(assistantText, 96);
  if (!userSummary && !assistantSummary) {
    return [] as PersonaEpisodeMemory[];
  }
  const title = userSummary.slice(0, 24) || assistantSummary.slice(0, 24) || "recent_episode";
  const text = normalizeText(
    [userSummary ? `user: ${userSummary}` : "", assistantSummary ? `assistant: ${assistantSummary}` : ""]
      .filter(Boolean)
      .join(" | "),
    180
  );
  return [
    {
      id: stableId(`episode:${text}`),
      kind: "episode" as const,
      title,
      text,
      keywords: tokenize(`${title} ${text}`),
      updatedAt,
      sourceTurnIds,
    },
  ];
}

export function emptyPersonaMemoryState(): PersonaMemoryState {
  return {
    version: PERSONA_MEMORY_VERSION,
    profile: [],
    facts: [],
    openLoops: [],
    episodes: [],
  };
}

export function parsePersonaMemoryState(value: unknown): PersonaMemoryState {
  let parsedValue = value;
  if (typeof value === "string") {
    try {
      parsedValue = JSON.parse(value || "null");
    } catch {
      parsedValue = null;
    }
  }
  const record = asRecord(parsedValue);
  if (!record) {
    return emptyPersonaMemoryState();
  }

  function parseItems<T extends { updatedAt: string; keywords: string[]; sourceTurnIds: string[] }>(
    items: unknown,
    builder: (item: Record<string, unknown>) => T | null
  ) {
    if (!Array.isArray(items)) {
      return [] as T[];
    }
    return items
      .map((item) => builder(asRecord(item) || {}))
      .filter((item): item is T => Boolean(item))
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
  }

  return {
    version: asString(record.version) || PERSONA_MEMORY_VERSION,
    profile: parseItems(record.profile, (item) => {
      const key = asString(item.key);
      const valueText = asString(item.value);
      if (!key || !valueText) return null;
      return {
        id: asString(item.id) || stableId(`profile:${key}:${valueText}`),
        kind: "profile" as const,
        key,
        value: valueText,
        keywords: uniqueStrings((Array.isArray(item.keywords) ? item.keywords : []).map(asString).concat(tokenize(`${key} ${valueText}`))),
        updatedAt: toIsoString(asString(item.updatedAt)),
        sourceTurnIds: uniqueStrings((Array.isArray(item.sourceTurnIds) ? item.sourceTurnIds : []).map(asString)),
      };
    }),
    facts: parseItems(record.facts, (item) => {
      const text = asString(item.text);
      if (!text) return null;
      return {
        id: asString(item.id) || stableId(`fact:${text}`),
        kind: "fact" as const,
        text,
        keywords: uniqueStrings((Array.isArray(item.keywords) ? item.keywords : []).map(asString).concat(tokenize(text))),
        updatedAt: toIsoString(asString(item.updatedAt)),
        sourceTurnIds: uniqueStrings((Array.isArray(item.sourceTurnIds) ? item.sourceTurnIds : []).map(asString)),
      };
    }),
    openLoops: parseItems(record.openLoops, (item) => {
      const text = asString(item.text);
      if (!text) return null;
      return {
        id: asString(item.id) || stableId(`open_loop:${text}`),
        kind: "open_loop" as const,
        text,
        keywords: uniqueStrings((Array.isArray(item.keywords) ? item.keywords : []).map(asString).concat(tokenize(text))),
        updatedAt: toIsoString(asString(item.updatedAt)),
        sourceTurnIds: uniqueStrings((Array.isArray(item.sourceTurnIds) ? item.sourceTurnIds : []).map(asString)),
      };
    }),
    episodes: parseItems(record.episodes, (item) => {
      const title = asString(item.title);
      const text = asString(item.text);
      if (!title || !text) return null;
      return {
        id: asString(item.id) || stableId(`episode:${title}:${text}`),
        kind: "episode" as const,
        title,
        text,
        keywords: uniqueStrings((Array.isArray(item.keywords) ? item.keywords : []).map(asString).concat(tokenize(`${title} ${text}`))),
        updatedAt: toIsoString(asString(item.updatedAt)),
        sourceTurnIds: uniqueStrings((Array.isArray(item.sourceTurnIds) ? item.sourceTurnIds : []).map(asString)),
      };
    }),
  };
}

export function updatePersonaMemoryState(input: {
  state: PersonaMemoryState;
  userText: string;
  assistantText: string;
  scenario?: string | null;
  sourceTurnIds?: string[];
  updatedAt?: string | Date | null;
}) {
  const sourceTurnIds = uniqueStrings(input.sourceTurnIds ?? []);
  const updatedAt = toIsoString(input.updatedAt);
  const scenarioText = normalizeText(input.scenario || "", 96);
  const extractionText = [input.userText, scenarioText].filter(Boolean).join(" ");
  const nextProfile = mergeByKey(
    input.state.profile.concat(extractProfileMemories(extractionText, sourceTurnIds, updatedAt)),
    (item) => normalizeKey(item.key),
    10
  );
  const nextFacts = mergeByKey(
    input.state.facts.concat(extractFactMemories(extractionText, sourceTurnIds, updatedAt)),
    (item) => normalizeKey(item.text),
    14
  );
  const nextOpenLoops = mergeByKey(
    input.state.openLoops.concat(extractOpenLoopMemories(input.userText, sourceTurnIds, updatedAt)),
    (item) => normalizeKey(item.text),
    8
  );
  const nextEpisodes = mergeByKey(
    input.state.episodes.concat(extractEpisodeMemories(input.userText, input.assistantText, sourceTurnIds, updatedAt)),
    (item) => normalizeKey(`${item.title}:${item.text}`),
    10
  );

  return {
    version: PERSONA_MEMORY_VERSION,
    profile: nextProfile,
    facts: nextFacts,
    openLoops: nextOpenLoops,
    episodes: nextEpisodes,
  } satisfies PersonaMemoryState;
}

export function seedPersonaMemoryState(input: { scenario?: string | null }) {
  const scenario = normalizeText(input.scenario || "", 120);
  if (!scenario) {
    return emptyPersonaMemoryState();
  }
  return updatePersonaMemoryState({
    state: emptyPersonaMemoryState(),
    userText: scenario,
    assistantText: "",
    scenario,
    sourceTurnIds: [],
  });
}

export function buildPersonaSummaryText(state: PersonaMemoryState) {
  const sections: string[] = [];
  if (state.profile.length > 0) {
    sections.push(
      "用户画像：\n" +
        trimList(state.profile, 6)
          .map((item) => `- ${item.key}: ${item.value}`)
          .join("\n")
    );
  }
  if (state.facts.length > 0) {
    sections.push(
      "关键事实：\n" +
        trimList(state.facts, 5)
          .map((item) => `- ${item.text}`)
          .join("\n")
    );
  }
  if (state.openLoops.length > 0) {
    sections.push(
      "待跟进问题：\n" +
        trimList(state.openLoops, 4)
          .map((item) => `- ${item.text}`)
          .join("\n")
    );
  }
  return sections.length > 0 ? sections.join("\n\n") : null;
}

export function recallPersonaMemory(input: {
  state: PersonaMemoryState;
  query: string;
  topFacts?: number;
  topEpisodes?: number;
  topOpenLoops?: number;
  includeProfile?: boolean;
}) {
  const queryTokens = tokenize(input.query);
  const rank = <T extends { keywords: string[]; updatedAt: string }>(items: T[]) =>
    items
      .map((item) => ({ item, score: overlapScore(queryTokens, item.keywords, item.updatedAt) }))
      .sort((left, right) => right.score - left.score || right.item.updatedAt.localeCompare(left.item.updatedAt))
      .map((item) => item.item);

  const profile = input.includeProfile !== false ? trimList(input.state.profile, 6) : [];
  const facts = trimList(rank(input.state.facts), input.topFacts ?? 4);
  const openLoops = trimList(rank(input.state.openLoops), input.topOpenLoops ?? 3);
  const episodes = trimList(rank(input.state.episodes), input.topEpisodes ?? 2);

  return {
    profile,
    facts,
    openLoops,
    episodes,
  } satisfies PersonaMemoryRecall;
}

export function buildPersonaMemoryMessages(input: {
  recall: PersonaMemoryRecall;
  toolNames: string[];
}) {
  const sections: string[] = [];
  if (input.recall.profile.length > 0) {
    sections.push(
      "Profile memory:\n" +
        input.recall.profile.map((item) => `- ${item.key}: ${item.value}`).join("\n")
    );
  }
  if (input.recall.openLoops.length > 0) {
    sections.push(
      "Open loops to stay consistent with:\n" +
        input.recall.openLoops.map((item) => `- ${item.text}`).join("\n")
    );
  }
  const recalledFacts = input.recall.facts.map((item) => `- ${item.text}`);
  const recalledEpisodes = input.recall.episodes.map((item) => `- ${item.title}: ${item.text}`);
  const recalled = recalledFacts.concat(recalledEpisodes);
  if (recalled.length > 0) {
    sections.push("Relevant recalled memory:\n" + recalled.join("\n"));
  }

  if (sections.length === 0) {
    return [] as PersonaMessage[];
  }

  return [
    {
      role: "system",
      content:
        [
          `Activated memory tools: ${input.toolNames.join(", ")}`,
          sections.join("\n\n"),
          "Use these memory notes only when they help answer the user more consistently and concretely.",
        ].join("\n\n"),
    },
  ] satisfies PersonaMessage[];
}
