import {
  DEFAULT_CONTEXT_BUILDER_VERSION,
  PersonaMessage,
  PersonaRole,
} from "./personaRuntime";

export interface PersonaTurn {
  id?: string;
  role: string;
  content: string;
}

export interface BuildPersonaContextInput {
  turns: PersonaTurn[];
  nextUserMessage?: string | null;
  systemPrompt?: string | null;
  summary?: string | null;
  extraMessages?: PersonaMessage[];
  maxInputTokens?: number | null;
  reserveOutputTokens?: number | null;
  maxRecentTurns?: number | null;
}

export interface BuildPersonaContextOutput {
  messages: PersonaMessage[];
  stableTurnIds: string[];
  orphanTurnIds: string[];
  estimatedPromptTokens: number | null;
  trimReport: Record<string, unknown>;
}

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeRole(value: string): PersonaRole | null {
  if (value === "system" || value === "user" || value === "assistant") {
    return value;
  }
  return null;
}

function estimateTokenCount(messages: PersonaMessage[]) {
  const totalChars = messages.reduce((sum, message) => sum + message.role.length + message.content.length + 8, 0);
  return Math.max(1, Math.ceil(totalChars / 4));
}

function buildTrimReport(input: {
  builderVersion: string;
  inputTurnCount: number;
  stableTurnIds: string[];
  orphanTurnIds: string[];
  droppedStableTurnIds: string[];
  droppedWindowTurnIds: string[];
  droppedSummary: boolean;
  extraMessageCount: number;
  systemPromptIncluded: boolean;
  summaryIncluded: boolean;
  maxInputTokens: number | null;
  reserveOutputTokens: number | null;
  maxRecentTurns: number | null;
  allowedPromptTokens: number | null;
  initialEstimatedPromptTokens: number | null;
  finalEstimatedPromptTokens: number | null;
  trimmedForBudget: boolean;
  hardBudgetExceeded: boolean;
}) {
  return {
    contextBuilderVersion: input.builderVersion,
    inputTurnCount: input.inputTurnCount,
    stableTurnCount: input.stableTurnIds.length,
    orphanTurnCount: input.orphanTurnIds.length,
    stableTurnIds: input.stableTurnIds,
    orphanTurnIds: input.orphanTurnIds,
    droppedStableTurnIds: input.droppedStableTurnIds,
    droppedWindowTurnIds: input.droppedWindowTurnIds,
    droppedSummary: input.droppedSummary,
    extraMessageCount: input.extraMessageCount,
    systemPromptIncluded: input.systemPromptIncluded,
    summaryIncluded: input.summaryIncluded,
    maxInputTokens: input.maxInputTokens,
    reserveOutputTokens: input.reserveOutputTokens,
    maxRecentTurns: input.maxRecentTurns,
    allowedPromptTokens: input.allowedPromptTokens,
    initialEstimatedPromptTokens: input.initialEstimatedPromptTokens,
    finalEstimatedPromptTokens: input.finalEstimatedPromptTokens,
    trimmedForBudget: input.trimmedForBudget,
    hardBudgetExceeded: input.hardBudgetExceeded,
  };
}

export function buildPersonaContext(input: BuildPersonaContextInput): BuildPersonaContextOutput {
  const stableTurns: Array<{ id: string; role: PersonaRole; content: string }> = [];
  const orphanTurns: Array<{ id: string; role: PersonaRole; content: string }> = [];

  for (const turn of input.turns) {
    const role = normalizeRole(asString(turn.role));
    const content = asString(turn.content);
    if (role === null || content.length === 0) {
      continue;
    }

    const id = asString(turn.id) || `turn_${stableTurns.length + orphanTurns.length}`;
    const last = stableTurns[stableTurns.length - 1];
    if (role === "user" && last?.role === "user") {
      orphanTurns.push(last);
      stableTurns[stableTurns.length - 1] = { id, role, content };
      continue;
    }

    stableTurns.push({ id, role, content });
  }

  while (stableTurns.length > 0 && stableTurns[stableTurns.length - 1]?.role === "user") {
    const trailing = stableTurns.pop();
    if (trailing) {
      orphanTurns.push(trailing);
    }
  }

  const stableTurnIds = stableTurns.map((turn) => turn.id);
  const orphanTurnIds = orphanTurns.map((turn) => turn.id);
  const systemPrompt = asString(input.systemPrompt);
  const summary = asString(input.summary);
  const nextUserMessage = asString(input.nextUserMessage);
  const extraMessages = Array.isArray(input.extraMessages)
    ? input.extraMessages
        .map((message) => ({
          role: normalizeRole(asString(message.role)) || "system",
          content: asString(message.content),
        }))
        .filter((message) => message.content.length > 0)
    : [];
  const maxInputTokens = input.maxInputTokens ?? null;
  const reserveOutputTokens = input.reserveOutputTokens ?? null;
  const maxRecentTurns = input.maxRecentTurns ?? null;
  const allowedPromptTokens =
    maxInputTokens !== null
      ? Math.max(0, maxInputTokens - Math.max(0, reserveOutputTokens ?? 0))
      : null;

  const droppedWindowTurnIds =
    maxRecentTurns !== null && maxRecentTurns >= 0 && stableTurns.length > maxRecentTurns
      ? stableTurns.slice(0, Math.max(0, stableTurns.length - maxRecentTurns)).map((turn) => turn.id)
      : [];
  const windowedStableTurns =
    maxRecentTurns !== null && maxRecentTurns >= 0 ? stableTurns.slice(-maxRecentTurns) : stableTurns.slice();

  const systemMessage: PersonaMessage[] = systemPrompt
    ? [{ role: "system", content: systemPrompt }]
    : [];
  const summaryMessage: PersonaMessage[] = summary
    ? [{ role: "system", content: `Conversation summary:\n${summary}` }]
    : [];
  const historyMessages: PersonaMessage[] = windowedStableTurns.map((turn) => ({
    role: turn.role,
    content: turn.content,
  }));
  if (nextUserMessage.length > 0) {
    historyMessages.push({ role: "user", content: nextUserMessage });
  }

  const initialMessages = systemMessage.concat(extraMessages, summaryMessage, historyMessages);
  const initialEstimatedPromptTokens = estimateTokenCount(initialMessages);

  let trimmedForBudget = false;
  let hardBudgetExceeded = false;
  let droppedSummary = false;
  const droppedStableTurnIds: string[] = [];

  let activeSummaryMessage = summaryMessage;
  const activeStableTurns = windowedStableTurns.slice();
  const userMessage = nextUserMessage.length > 0 ? historyMessages[historyMessages.length - 1] : null;

  const buildMessages = () =>
    systemMessage.concat(
      extraMessages,
      activeSummaryMessage,
      activeStableTurns.map((turn) => ({
        role: turn.role,
        content: turn.content,
      })),
      userMessage ? [userMessage] : []
    );

  let finalMessages = buildMessages();
  let finalEstimatedPromptTokens = estimateTokenCount(finalMessages);

  if (allowedPromptTokens !== null && finalEstimatedPromptTokens > allowedPromptTokens) {
    trimmedForBudget = true;

    while (finalEstimatedPromptTokens > allowedPromptTokens && activeStableTurns.length > 0) {
      const removed = activeStableTurns.shift();
      if (removed) {
        droppedStableTurnIds.push(removed.id);
      }
      finalMessages = buildMessages();
      finalEstimatedPromptTokens = estimateTokenCount(finalMessages);
    }

    if (finalEstimatedPromptTokens > allowedPromptTokens && activeSummaryMessage.length > 0) {
      activeSummaryMessage = [];
      droppedSummary = true;
      finalMessages = buildMessages();
      finalEstimatedPromptTokens = estimateTokenCount(finalMessages);
    }

    if (finalEstimatedPromptTokens > allowedPromptTokens) {
      hardBudgetExceeded = true;
    }
  }

  return {
    messages: finalMessages,
    stableTurnIds: activeStableTurns.map((turn) => turn.id),
    orphanTurnIds,
    estimatedPromptTokens: finalEstimatedPromptTokens,
    trimReport: buildTrimReport({
      builderVersion: DEFAULT_CONTEXT_BUILDER_VERSION,
      inputTurnCount: input.turns.length,
      stableTurnIds,
      orphanTurnIds,
      droppedStableTurnIds,
      droppedWindowTurnIds,
      droppedSummary,
      extraMessageCount: extraMessages.length,
      systemPromptIncluded: systemMessage.length > 0,
      summaryIncluded: activeSummaryMessage.length > 0,
      maxInputTokens,
      reserveOutputTokens,
      maxRecentTurns,
      allowedPromptTokens,
      initialEstimatedPromptTokens,
      finalEstimatedPromptTokens,
      trimmedForBudget,
      hardBudgetExceeded,
    }),
  };
}
