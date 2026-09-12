import { describe, expect, it } from "vitest";
import type { RecordOut, RecordStatus } from "@/features/records/api/types";
import { buildLearningChain } from "@/features/courses/courseLearningChain";

const STATUSES: RecordStatus[] = [
  "FAILED",
  "COMPLETED",
  "SUMMARY_READY",
  "SUMMARY_PROCESSING",
  "SUMMARY_PENDING",
  "CONTENT_PROCESSING",
  "DRAFT",
  "NOTE",
];

function record(status: RecordStatus, index: number): RecordOut {
  return {
    id: `record-${index}`,
    course_id: "course-1",
    capture_type: "QUICK_NOTE",
    title: `记录 ${index}`,
    status,
    duration_ms: 0,
    summary_confirmed_at: null,
    created_at: "2026-08-19T08:00:00.000000Z",
    updated_at: "2026-08-19T08:00:00.000000Z",
  };
}

const allStatusRecords = STATUSES.map(record);

function flowTotal(
  flows: ReturnType<typeof buildLearningChain>["flows"],
  key: "source" | "target",
  node: string,
) {
  return flows
    .filter((flow) => flow[key] === node)
    .reduce((sum, flow) => sum + flow.value, 0);
}

describe("buildLearningChain", () => {
  it("按八态派生各阶段到达数与停留分布", () => {
    const chain = buildLearningChain(allStatusRecords);
    expect(chain.total).toBe(8);
    expect(chain.reached).toEqual({
      capture: 8,
      transcribe: 5,
      summary: 4,
      confirm: 1,
    });
    expect(chain.drops).toEqual({
      notStarted: 2,
      transcribing: 1,
      summarizing: 2,
      pendingConfirm: 1,
      failed: 1,
    });
  });

  it("流转守恒：内部节点流入等于流出，终端节点只进不出", () => {
    const { flows, total } = buildLearningChain(allStatusRecords);
    expect(flowTotal(flows, "source", "capture")).toBe(total);
    for (const node of ["transcribe", "summary"] as const) {
      expect(flowTotal(flows, "source", node)).toBe(
        flowTotal(flows, "target", node),
      );
    }
    for (const node of [
      "confirm",
      "notStarted",
      "transcribing",
      "summarizing",
      "pendingConfirm",
      "failed",
    ] as const) {
      expect(flowTotal(flows, "source", node)).toBe(0);
    }
  });

  it("阶段到达率取整数百分比", () => {
    const chain = buildLearningChain(allStatusRecords);
    expect(chain.conversion).toEqual({
      capture: 100,
      transcribe: 63,
      summary: 50,
      confirm: 13,
    });
  });

  it("空列表不产生流转且不除零", () => {
    const chain = buildLearningChain([]);
    expect(chain.total).toBe(0);
    expect(chain.flows).toEqual([]);
    expect(chain.conversion).toEqual({
      capture: 0,
      transcribe: 0,
      summary: 0,
      confirm: 0,
    });
  });

  it("仅失败记录时只保留捕获到失败的分支", () => {
    const chain = buildLearningChain([record("FAILED", 1)]);
    expect(chain.flows).toEqual([
      { source: "capture", target: "failed", value: 1 },
    ]);
    expect(chain.reached.transcribe).toBe(0);
    expect(chain.drops.pendingConfirm).toBe(0);
  });
});
