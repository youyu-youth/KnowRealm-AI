// 课堂详情「学习链」真实派生：记录状态 → 阶段到达数、停留分布与守恒的流转。
// 口径：到达某阶段 = 进入该阶段（进行中也算）；停留 = 当前停在该阶段的记录。
// 记录不保存「失败发生在哪个阶段」，失败只作捕获侧分支并在界面明示该口径。
import type { RecordOut, RecordStatus } from "@/features/records/api/types";

export type LearningChainStageKey =
  "capture" | "transcribe" | "summary" | "confirm";

export type LearningChainDropKey =
  "notStarted" | "transcribing" | "summarizing" | "pendingConfirm" | "failed";

export type LearningChainNodeKey = LearningChainStageKey | LearningChainDropKey;

export type LearningChainFlow = {
  source: LearningChainNodeKey;
  target: LearningChainNodeKey;
  value: number;
};

export type LearningChain = {
  /** 记录总数（含失败） */
  total: number;
  /** 各阶段到达数 */
  reached: Record<LearningChainStageKey, number>;
  /** 各阶段停留数 */
  drops: Record<LearningChainDropKey, number>;
  /** 非零流转（守恒：每个节点流入 == 流出） */
  flows: LearningChainFlow[];
  /** 阶段到达率（整数百分比，相对总数） */
  conversion: Record<LearningChainStageKey, number>;
};

export const LEARNING_CHAIN_STAGE_KEYS: LearningChainStageKey[] = [
  "capture",
  "transcribe",
  "summary",
  "confirm",
];

export const LEARNING_CHAIN_DROP_KEYS: LearningChainDropKey[] = [
  "notStarted",
  "transcribing",
  "summarizing",
  "pendingConfirm",
  "failed",
];

const REACHED_TRANSCRIBE: RecordStatus[] = [
  "CONTENT_PROCESSING",
  "SUMMARY_PENDING",
  "SUMMARY_PROCESSING",
  "SUMMARY_READY",
  "COMPLETED",
];

const REACHED_SUMMARY: RecordStatus[] = [
  "SUMMARY_PENDING",
  "SUMMARY_PROCESSING",
  "SUMMARY_READY",
  "COMPLETED",
];

function percent(count: number, total: number): number {
  return total === 0 ? 0 : Math.round((count / total) * 100);
}

export function buildLearningChain(records: RecordOut[]): LearningChain {
  const countOf = (statuses: RecordStatus[]) =>
    records.filter((record) => statuses.includes(record.status)).length;

  const total = records.length;
  const reached: LearningChain["reached"] = {
    capture: total,
    transcribe: countOf(REACHED_TRANSCRIBE),
    summary: countOf(REACHED_SUMMARY),
    confirm: countOf(["COMPLETED"]),
  };
  const drops: LearningChain["drops"] = {
    notStarted: countOf(["NOTE", "DRAFT"]),
    transcribing: countOf(["CONTENT_PROCESSING"]),
    summarizing: countOf(["SUMMARY_PENDING", "SUMMARY_PROCESSING"]),
    pendingConfirm: countOf(["SUMMARY_READY"]),
    failed: countOf(["FAILED"]),
  };

  const flows = (
    [
      { source: "capture", target: "transcribe", value: reached.transcribe },
      { source: "capture", target: "notStarted", value: drops.notStarted },
      { source: "capture", target: "failed", value: drops.failed },
      { source: "transcribe", target: "summary", value: reached.summary },
      {
        source: "transcribe",
        target: "transcribing",
        value: drops.transcribing,
      },
      { source: "summary", target: "confirm", value: reached.confirm },
      { source: "summary", target: "summarizing", value: drops.summarizing },
      {
        source: "summary",
        target: "pendingConfirm",
        value: drops.pendingConfirm,
      },
    ] satisfies LearningChainFlow[]
  ).filter((flow) => flow.value > 0);

  return {
    total,
    reached,
    drops,
    flows,
    conversion: {
      capture: percent(reached.capture, total),
      transcribe: percent(reached.transcribe, total),
      summary: percent(reached.summary, total),
      confirm: percent(reached.confirm, total),
    },
  };
}
