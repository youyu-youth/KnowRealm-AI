export type DraftItem = Record<string, unknown>;
export type FlatEntry = { phaseTitle: string; item: DraftItem };

/** 载荷 phases → 摊平条目（编辑与排序的全列表视角）。形状漂变时返回空。 */
export function flatten(payload: Record<string, unknown>): FlatEntry[] {
  const phases = Array.isArray(payload.phases)
    ? payload.phases.filter(
        (phase): phase is Record<string, unknown> =>
          typeof phase === "object" && phase !== null,
      )
    : [];
  const entries: FlatEntry[] = [];
  for (const phase of phases) {
    const title = typeof phase.title === "string" ? phase.title : "";
    const items = Array.isArray(phase.items)
      ? phase.items.filter(
          (item): item is DraftItem =>
            typeof item === "object" && item !== null,
        )
      : [];
    for (const item of items) {
      entries.push({ phaseTitle: title, item });
    }
  }
  return entries;
}

/** 编辑后载荷的计划项计数（确认按钮的零项守卫）。 */
export function planDraftItemCount(payload: Record<string, unknown>): number {
  return flatten(payload).length;
}
