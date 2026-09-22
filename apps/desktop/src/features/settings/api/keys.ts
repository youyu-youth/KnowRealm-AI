export const settingsKeys = {
  dataDirectory: ["settings", "data-directory"] as const,
  libraryState: ["settings", "data-directory-library"] as const,
  llmProvider: ["settings", "llm-provider"] as const,
  llmUsage: ["settings", "llm-usage"] as const,
  tencentAsrProvider: ["settings", "tencent-asr-provider"] as const,
  webSearchProvider: ["settings", "web-search-provider"] as const,
  preferences: ["settings", "preferences"] as const,
  profile: ["settings", "profile"] as const,
  learnerMemory: ["settings", "learner-memory"] as const,
  profileAvatar: ["settings", "profile-avatar"] as const,
  operationRuns: ["settings", "operation-runs"] as const,
  operationRunDetail: (runId: string) =>
    ["settings", "operation-runs", runId] as const,
  operations: ["settings", "operations"] as const,
  agentActivity: ["settings", "agent-activity"] as const,
};
