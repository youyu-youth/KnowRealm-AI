import type {
  ConceptAnchorSource,
  ConceptKpSource,
} from "@/features/courses/api/types";

type RecordJump = {
  to: "/records/$recordId";
  params: { recordId: string };
  search: {
    tab: "transcript" | "knowledge-points";
    highlight?: string;
    segmentId?: string;
  };
};

type ChatJump = {
  to: "/chat/$sessionId";
  params: { sessionId: string };
};

export type SourceJump = RecordJump | ChatJump;

/**
 * 锚点跳转目标（grill Q7）：转写/文档/速记锚点落到记录转写视图，segmentId
 * 精确定位到锚点分片（同一摘录多次出现时不误落首次），quote 非空时作为
 * 定位摘录（TranscriptPanel 分片 id 未命中时按文本回落，找不到提示原文已
 * 变动）；对话锚点直达会话。无 record_id 且非对话的锚点返回 null，退化为
 * 纯文本行。
 */
export function anchorJumpTarget(
  anchor: ConceptAnchorSource,
): SourceJump | null {
  if (anchor.source_type === "CHAT_MESSAGE") {
    return anchor.chat_session_id
      ? {
          to: "/chat/$sessionId",
          params: { sessionId: anchor.chat_session_id },
        }
      : null;
  }
  if (!anchor.record_id) return null;
  const quote = anchor.quote?.trim();
  return {
    to: "/records/$recordId",
    params: { recordId: anchor.record_id },
    search: {
      tab: "transcript",
      ...(anchor.segment_id ? { segmentId: anchor.segment_id } : {}),
      ...(quote ? { highlight: quote } : {}),
    },
  };
}

/** 知识点来源跳到该记录的知识点面板（锚点定位由面板自身组织，不跨面板传摘录）。 */
export function knowledgePointJumpTarget(kp: ConceptKpSource): RecordJump {
  return {
    to: "/records/$recordId",
    params: { recordId: kp.record_id },
    search: { tab: "knowledge-points" },
  };
}
