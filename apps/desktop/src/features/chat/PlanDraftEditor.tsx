import type { TFunction } from "i18next";
import { ArrowDown, ArrowUp, PencilLine, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** 确认卡草案编辑器（通用 Agent 第三阶段工单 03，spec 用户故事 9）：
 * 改日期 / 改时长 / 删项 / 排序四操作，确认时按编辑结果落库（服务端校验
 * 边界：日期不早于今天、不晚于目标期限；至少保留一个计划项）。
 *
 * 受控组件：payload 是提案载荷的浅拷贝形状（phases[].items[]），每次编辑
 * 经 onChange 上抛完整新载荷；排序按全列表相邻交换实现，跨阶段边界时项
 * 自动流转到相邻阶段（重建时按连续同名阶段分组，空阶段自然消失）。 */

export type DraftEditorProps = {
  payload: Record<string, unknown>;
  snapshot?: Record<string, unknown> | null;
  onChange: (next: Record<string, unknown>) => void;
  t: TFunction;
};

type DraftItem = Record<string, unknown>;
type DraftPhase = { title: string; items: DraftItem[] };

type FlatEntry = { phaseTitle: string; item: DraftItem };

const PLAN_ITEM_TYPE_KEYS: Record<string, string> = {
  STUDY_RECORD: "chat.operationProposal.planFields.itemType.STUDY_RECORD",
  PRACTICE_QUIZ: "chat.operationProposal.planFields.itemType.PRACTICE_QUIZ",
  REVIEW_CONCEPT: "chat.operationProposal.planFields.itemType.REVIEW_CONCEPT",
  CUSTOM: "chat.operationProposal.planFields.itemType.CUSTOM",
};

/** 载荷 phases → 摊平条目（编辑与排序的全列表视角）。形状漂变时返回空。 */
function flatten(payload: Record<string, unknown>): FlatEntry[] {
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

/** 不可变更新条目 item 的字段。 */
function patchItem(
  entries: FlatEntry[],
  index: number,
  patch: Record<string, unknown>,
): FlatEntry[] {
  return entries.map((entry, i) =>
    i === index ? { ...entry, item: { ...entry.item, ...patch } } : entry,
  );
}

/** 摊平条目 → 载荷 phases（连续同名阶段合并，空阶段消失）。 */
function rebuild(entries: FlatEntry[]): DraftPhase[] {
  const phases: DraftPhase[] = [];
  for (const { phaseTitle, item } of entries) {
    const last = phases[phases.length - 1];
    if (last !== undefined && last.title === phaseTitle) {
      last.items.push(item);
    } else {
      phases.push({ title: phaseTitle, items: [item] });
    }
  }
  return phases;
}

export function PlanDraftEditor({
  payload,
  snapshot,
  onChange,
  t,
}: DraftEditorProps) {
  const entries = flatten(payload);
  const goalId = typeof payload.goal_id === "string" ? payload.goal_id : "";
  const snapshotTitle =
    typeof snapshot?.title === "string" ? snapshot.title : "";
  const snapshotCourse =
    typeof snapshot?.course_name === "string" ? snapshot.course_name : "";
  const dates = entries
    .map(({ item }) =>
      typeof item.scheduled_date === "string" ? item.scheduled_date : "",
    )
    .filter(Boolean)
    .sort();
  const totalMinutes = entries.reduce(
    (total, { item }) =>
      total +
      (typeof item.estimated_minutes === "number" ? item.estimated_minutes : 0),
    0,
  );

  const emit = (next: FlatEntry[]) => {
    onChange({ goal_id: goalId, phases: rebuild(next) });
  };

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= entries.length) return;
    const next = [...entries];
    [next[index], next[target]] = [next[target]!, next[index]!];
    emit(next);
  };

  return (
    <div className="flex w-full flex-col gap-1.5">
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        <span className="text-label text-ink min-w-0 font-medium break-words">
          {snapshotTitle || goalId}
        </span>
        <span className="text-label text-muted-foreground">
          {snapshotCourse}
        </span>
      </div>
      <p className="text-label text-muted-foreground">
        {dates.length > 0
          ? t("chat.operationProposal.planConfirm.scheduleSummary", {
              count: entries.length,
              minutes: totalMinutes,
              from: dates[0],
              to: dates[dates.length - 1],
            })
          : t("chat.operationProposal.planConfirm.scheduleEmpty")}
      </p>
      <p className="text-label text-muted-foreground flex items-center gap-1.5">
        <PencilLine className="text-ink-faint size-3.5" aria-hidden="true" />
        {t("chat.operationProposal.planEdit.hint")}
      </p>
      <ul className="flex flex-col gap-1">
        {entries.map(({ phaseTitle, item }, index) => {
          const scheduledDate =
            typeof item.scheduled_date === "string" ? item.scheduled_date : "";
          const minutes =
            typeof item.estimated_minutes === "number"
              ? item.estimated_minutes
              : Number.parseInt(String(item.estimated_minutes ?? ""), 10);
          const itemType =
            typeof item.action_type === "string" ? item.action_type : "";
          return (
            <li
              key={`${phaseTitle}-${index}`}
              className="text-label text-ink-muted flex flex-col gap-0.5"
            >
              {entries[index - 1]?.phaseTitle !== phaseTitle ? (
                <p className="text-ink-muted font-medium">
                  {phaseTitle ||
                    t("chat.operationProposal.planConfirm.unnamedPhase")}
                </p>
              ) : null}
              <span className="flex flex-wrap items-center gap-1.5">
                <Input
                  type="date"
                  aria-label={t("chat.operationProposal.planEdit.dateAria")}
                  className="text-label h-7 w-[9.5rem] px-1.5"
                  value={scheduledDate}
                  onChange={(event) =>
                    emit(
                      patchItem(entries, index, {
                        scheduled_date: event.target.value,
                      }),
                    )
                  }
                />
                <span className="min-w-0 flex-1 break-words">
                  {typeof item.content === "string" ? item.content : ""}
                </span>
                {PLAN_ITEM_TYPE_KEYS[itemType] ? (
                  <span className="text-ink-faint shrink-0">
                    {t(PLAN_ITEM_TYPE_KEYS[itemType])}
                  </span>
                ) : null}
                <Input
                  type="number"
                  min={1}
                  max={600}
                  aria-label={t("chat.operationProposal.planEdit.minutesAria")}
                  className="text-label h-7 w-[5.5rem] px-1.5"
                  value={Number.isFinite(minutes) ? minutes : ""}
                  onChange={(event) => {
                    const parsed = Number.parseInt(event.target.value, 10);
                    if (Number.isFinite(parsed) && parsed > 0) {
                      emit(
                        patchItem(entries, index, {
                          estimated_minutes: parsed,
                        }),
                      );
                    }
                  }}
                />
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={t("chat.operationProposal.planEdit.moveUp")}
                  disabled={index === 0}
                  onClick={() => move(index, -1)}
                >
                  <ArrowUp className="size-3.5" aria-hidden="true" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={t("chat.operationProposal.planEdit.moveDown")}
                  disabled={index === entries.length - 1}
                  onClick={() => move(index, 1)}
                >
                  <ArrowDown className="size-3.5" aria-hidden="true" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={t("chat.operationProposal.planEdit.remove")}
                  onClick={() => emit(entries.filter((_, i) => i !== index))}
                >
                  <Trash2 className="size-3.5" aria-hidden="true" />
                </Button>
              </span>
              {typeof item.reason === "string" && item.reason ? (
                <span className="text-ink-faint break-words">
                  {t("chat.operationProposal.planFields.reasonLabel") +
                    item.reason}
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
      {entries.length === 0 ? (
        <p role="alert" className="text-destructive text-label">
          {t("chat.operationProposal.planEdit.emptyDraft")}
        </p>
      ) : null}
    </div>
  );
}
