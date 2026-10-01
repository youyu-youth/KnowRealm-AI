import { type ComponentType, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Check, RefreshCw, Undo2, X } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import {
  libraryApi,
  type AgentProposalOut,
} from "@/features/library/api/library";
import { libraryKeys } from "@/features/library/api/keys";
import { sharedRefsKeys } from "@/features/sharedRefs/api/keys";
import { agentKeys } from "@/features/agent/api/authMode";
import {
  operationHistoryApi,
  type AgentOperationOut,
} from "@/features/settings/api/operationHistory";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import {
  PlanDraftEditor,
  planDraftItemCount,
  type DraftEditorProps,
} from "@/features/chat/PlanDraftEditor";
import {
  PLAN_ITEM_TYPE_KEYS,
  isPlanItemType,
} from "@/features/learningPlan/planItemTypes";
import { Button } from "@/components/ui/button";

type ChatOperationProposalCardProps = {
  sessionId: string;
  /** 父级聊天发送（重新生成入口代发指令消息）：传入时 plan 草案卡渲染第三按钮
   * （放弃旧草案 + 让 Agent 重排一份；旧草案以 REJECTED 终态失效）。 */
  onSendMessage?: (text: string) => void;
};

/** 确认/拒绝成功后的即时覆盖层：免去等 refetch 的空窗闪烁；远端到位后两者一致。 */
type DecisionOverride = {
  status: "APPLIED" | "REJECTED";
  result: Record<string, unknown> | null;
};

type PreviewFieldsProps = {
  payload: Record<string, unknown>;
  /** 执行前快照（工单 03）：修改类动作 before/after 预览的旧值来源。 */
  snapshot: Record<string, unknown> | null;
  t: TFunction;
};

type SettledRowProps = {
  status: AgentProposalOut["status"];
  result: Record<string, unknown> | null;
  t: TFunction;
};

/** 提案 payload → 课程创建确认卡字段行（标签复用新建课程表单文案，枚举值走既有翻译）。 */
function previewRows(
  payload: Record<string, unknown>,
  t: (key: string) => string,
): { label: string; value: string }[] {
  const str = (key: string) =>
    typeof payload[key] === "string" ? (payload[key] as string) : null;
  const rows: { label: string; value: string }[] = [];
  const push = (label: string, value: string | null) => {
    if (value) rows.push({ label, value });
  };
  push(t("spaces.form.name"), str("name"));
  const context = str("learning_context");
  push(
    t("spaces.form.learningContext"),
    context ? t(`spaces.learningContext.${context}`) : null,
  );
  const stage = str("education_stage");
  push(
    t("spaces.form.educationStage"),
    stage ? t(`spaces.educationStage.${stage}`) : null,
  );
  const depth = str("depth");
  push(t("spaces.form.depth"), depth ? t(`spaces.depth.${depth}`) : null);
  const courseType = str("course_type");
  push(
    t("spaces.form.courseType"),
    courseType ? t(`spaces.courseType.${courseType}`) : null,
  );
  push(t("spaces.form.courseDescription"), str("description"));
  return rows;
}

/** TEXT_RECORD_ADD 正文摘要：折叠空白并截断到单行可读长度（全文在记录页）。 */
function contentExcerpt(content: unknown): string | null {
  if (typeof content !== "string" || !content.trim()) return null;
  const flat = content.replace(/\s+/g, " ").trim();
  return flat.length > 120 ? `${flat.slice(0, 120)}…` : flat;
}

/** 提案 payload / result 投影的字符串窄化（形状漂移时返回 null 兜底）。 */
function fieldString(
  source: Record<string, unknown> | null | undefined,
  key: string,
): string | null {
  const value = source?.[key];
  return typeof value === "string" ? value : null;
}

/** 回执总结任务三态（spec 决策 15：已保存 ≠ 总结已生成 ≠ 可检索）：
 * 提交成功 → 已提交生成中；提交失败 → 失败原因 + 记录页重试指引；均无 → 未触发
 * （AI 未配置或未同意外发，读取 result 投影的窄化字段）。 */
function summaryStateText(
  result: Record<string, unknown> | null,
  t: TFunction,
): string {
  const summaryJobId = fieldString(result, "summary_job_id");
  const summaryErrorCode = fieldString(result, "summary_error_code");
  if (summaryJobId) {
    return t("chat.operationProposal.textRecord.summaryJobSubmitted");
  }
  if (summaryErrorCode) {
    return t("chat.operationProposal.textRecord.summaryFailed", {
      reason: t(`errors.${summaryErrorCode}`, summaryErrorCode),
    });
  }
  return t("chat.operationProposal.textRecord.summaryNotTriggered");
}

/** TEXT_RECORD_ADD 确认卡的目标课程名：经既有课程 API 按 id 拉取（spec 决策 14，
 * 确认卡预览不交付课程详情读取工具）；课程已删/不可读时如实提示。 */
function TextRecordCourseName({ courseId }: { courseId: string }) {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: courseKeys.detail(courseId),
    queryFn: () => courseApi.get(courseId),
    staleTime: 30_000,
    retry: false,
  });
  if (query.isError) {
    return (
      <span className="text-muted-foreground">
        {t("chat.operationProposal.textRecord.courseUnavailable")}
      </span>
    );
  }
  return <>{query.data?.name ?? courseId}</>;
}

// ---------------------------------------------------------------------------
// 类型专属卡片行为（03 review 收敛）：文案键、预览字段行与回执行的差异全部
// 聚合进下方 CARD_BY_TYPE 配置表——新操作接入 = 表加一行 + 两个新组件，
// 分派点零改动（先例：ToolActivityCard 的 TOOL_ACTIVITY_META 单映射）。
// ---------------------------------------------------------------------------

/** 修改类 before/after 预览的展示值截断（长说明等单行可读）。 */
function excerpt(value: string, max = 40): string {
  const flat = value.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max)}…` : flat;
}

/** 课程修改字段的展示顺序与枚举翻译（键集 = OP_COURSE_UPDATE 可修改字段）。 */
const COURSE_FIELD_LABEL_KEYS: Record<string, string> = {
  name: "spaces.form.name",
  learning_context: "spaces.form.learningContext",
  education_stage: "spaces.form.educationStage",
  depth: "spaces.form.depth",
  course_type: "spaces.form.courseType",
  description: "spaces.form.courseDescription",
};

const COURSE_FIELD_ENUM_PREFIXES: Record<string, string> = {
  learning_context: "spaces.learningContext.",
  education_stage: "spaces.educationStage.",
  depth: "spaces.depth.",
  course_type: "spaces.courseType.",
};

function courseFieldDisplay(
  key: string,
  value: unknown,
  t: TFunction,
): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value);
  const prefix = COURSE_FIELD_ENUM_PREFIXES[key];
  return prefix ? t(`${prefix}${text}`) : excerpt(text);
}

/** 修改类共用的 before → after 行（旧值缺失时仅呈现新值；label 已是翻译文本）。 */
function BeforeAfterRows({
  entries,
}: {
  entries: { label: string; before: string | null; after: string }[];
}) {
  return (
    <>
      {entries.map((entry) => (
        <div
          key={entry.label}
          className="flex min-w-0 flex-wrap items-center gap-1.5"
        >
          <dt className="text-label text-muted-foreground shrink-0">
            {entry.label}
          </dt>
          {entry.before !== null ? (
            <>
              <dd className="text-label text-ink-muted decoration-border-strong break-words line-through">
                {entry.before}
              </dd>
              <ArrowRight
                className="text-ink-faint size-3 shrink-0"
                aria-hidden="true"
              />
            </>
          ) : null}
          <dd className="text-label text-ink min-w-0 break-words">
            {entry.after}
          </dd>
        </div>
      ))}
    </>
  );
}

/** COURSE_CREATE 确认卡预览：完整参数行（枚举值走表单文案翻译）。 */
function CourseCreatePreviewFields({ payload, t }: PreviewFieldsProps) {
  return (
    <>
      {previewRows(payload, t).map((row) => (
        <div key={row.label} className="flex gap-2">
          <dt className="text-label text-muted-foreground shrink-0">
            {row.label}
          </dt>
          <dd className="text-label text-ink min-w-0 break-words">
            {row.value}
          </dd>
        </div>
      ))}
    </>
  );
}

/** OP_COURSE_UPDATE 确认卡预览：目标课程 + 修改字段 before/after（payload
 * 中非空值字段才是本次要修改的字段，before 读执行前快照）。 */
function CourseUpdatePreviewFields({
  payload,
  snapshot,
  t,
}: PreviewFieldsProps) {
  const entries: { label: string; before: string | null; after: string }[] = [];
  for (const [key, labelKey] of Object.entries(COURSE_FIELD_LABEL_KEYS)) {
    const after = courseFieldDisplay(key, payload[key], t);
    if (after === null) continue;
    entries.push({
      label: t(labelKey),
      before: snapshot ? courseFieldDisplay(key, snapshot[key], t) : null,
      after,
    });
  }
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.modify.targetCourse")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {fieldString(snapshot, "name") ?? fieldString(payload, "course_id")}
        </dd>
      </div>
      <BeforeAfterRows entries={entries} />
    </>
  );
}

/** 课程 / 条目归档与恢复类预览：目标对象行 + 影响提示行。 */
function StatusChangePreviewFields({
  targetLabelKey,
  targetName,
  hintKey,
  t,
}: {
  targetLabelKey: string;
  targetName: string | null;
  hintKey: string;
  t: TFunction;
}) {
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t(targetLabelKey)}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {targetName}
        </dd>
      </div>
      <p className="text-label text-muted-foreground">{t(hintKey)}</p>
    </>
  );
}

function CourseArchivePreviewFields({ snapshot }: PreviewFieldsProps) {
  const { t } = useTranslation();
  return StatusChangePreviewFields({
    targetLabelKey: "chat.operationProposal.modify.targetCourse",
    targetName: fieldString(snapshot, "name"),
    hintKey: "chat.operationProposal.courseArchive.hint",
    t,
  });
}

function CourseRestorePreviewFields({ snapshot }: PreviewFieldsProps) {
  const { t } = useTranslation();
  return StatusChangePreviewFields({
    targetLabelKey: "chat.operationProposal.modify.targetCourse",
    targetName: fieldString(snapshot, "name"),
    hintKey: "chat.operationProposal.courseRestore.hint",
    t,
  });
}

/** OP_UNDO 确认卡预览（工单 06）：撤销哪个操作（id 缩写）＋目标当前名（快照，
 * 撤销时将恢复该操作执行前的值；确认前目标被改 → 撤销前重验拒绝）。 */
function UndoPreviewFields({ payload, snapshot, t }: PreviewFieldsProps) {
  const operationId = fieldString(payload, "operation_id");
  return StatusChangePreviewFields({
    targetLabelKey: "chat.operationProposal.undo.target",
    targetName:
      fieldString(snapshot, "title") ??
      fieldString(snapshot, "name") ??
      (operationId ? `#${operationId.slice(0, 8)}` : null),
    hintKey: "chat.operationProposal.undo.hint",
    t,
  });
}

/** OP_UNDO 回执行：已撤销（补偿操作已执行）/ 已取消撤销。 */
function SettledUndoRow({ status, t }: SettledRowProps) {
  return (
    <p className="text-label text-muted-foreground w-full">
      {status === "APPLIED"
        ? t("chat.operationProposal.undo.accepted")
        : t("chat.operationProposal.undo.rejected")}
    </p>
  );
}

/** OP_LIBRARY_ITEM_UPDATE 确认卡预览：目标条目 + 标题 / 归类 before/after
 * （课程名经课程 API 按 id 拉取，未归类＝占位文案）。 */
function LibraryItemUpdatePreviewFields({
  payload,
  snapshot,
  t,
}: PreviewFieldsProps) {
  const titleEntries: {
    label: string;
    before: string | null;
    after: string;
  }[] = [];
  if (typeof payload.title === "string" && payload.title) {
    titleEntries.push({
      label: t("chat.operationProposal.libraryItemUpdate.titleField"),
      before: snapshot
        ? excerpt(fieldString(snapshot, "title") ?? "") || null
        : null,
      after: excerpt(payload.title),
    });
  }
  const beforeCourseId = fieldString(snapshot, "course_id");
  const afterCourseId = fieldString(payload, "course_id");
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.modify.targetItem")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {fieldString(snapshot, "title") ?? fieldString(payload, "item_id")}
        </dd>
      </div>
      <BeforeAfterRows entries={titleEntries} />
      {afterCourseId ? (
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <dt className="text-label text-muted-foreground shrink-0">
            {t("chat.operationProposal.libraryItemUpdate.courseField")}
          </dt>
          {snapshot && beforeCourseId ? (
            <>
              <dd className="text-label text-ink-muted decoration-border-strong break-words line-through">
                <TextRecordCourseName courseId={beforeCourseId} />
              </dd>
              <ArrowRight
                className="text-ink-faint size-3 shrink-0"
                aria-hidden="true"
              />
            </>
          ) : null}
          <dd className="text-label text-ink min-w-0 break-words">
            <TextRecordCourseName courseId={afterCourseId} />
          </dd>
        </div>
      ) : null}
    </>
  );
}

function LibraryItemArchivePreviewFields({ snapshot }: PreviewFieldsProps) {
  const { t } = useTranslation();
  return StatusChangePreviewFields({
    targetLabelKey: "chat.operationProposal.modify.targetItem",
    targetName: fieldString(snapshot, "title"),
    hintKey: "chat.operationProposal.libraryItemArchive.hint",
    t,
  });
}

function LibraryItemRestorePreviewFields({ snapshot }: PreviewFieldsProps) {
  const { t } = useTranslation();
  return StatusChangePreviewFields({
    targetLabelKey: "chat.operationProposal.modify.targetItem",
    targetName: fieldString(snapshot, "title"),
    hintKey: "chat.operationProposal.libraryItemRestore.hint",
    t,
  });
}

/** 提案快照的数值窄化（记录删除影响计数等，形状漂移返回 null）。 */
function fieldNumber(
  source: Record<string, unknown> | null | undefined,
  key: string,
): number | null {
  const value = source?.[key];
  return typeof value === "number" ? value : null;
}

/** OP_RECORD_SOFT_DELETE 确认卡预览：目标记录 + 记录级资产计数 + 删除
 * 不可逆警告（L3 高风险动作，确认卡完整呈现级联影响）。 */
function RecordSoftDeletePreviewFields({ snapshot, t }: PreviewFieldsProps) {
  const countLabels: string[] = [];
  if (typeof snapshot?.has_summary === "boolean") {
    countLabels.push(
      t(
        snapshot.has_summary
          ? "chat.operationProposal.recordDelete.hasSummary"
          : "chat.operationProposal.recordDelete.noSummary",
      ),
    );
  }
  const countEntries: [string, string][] = [
    ["knowledge_point_count", "chat.operationProposal.recordDelete.kpCount"],
    ["quiz_count", "chat.operationProposal.recordDelete.quizCount"],
    ["todo_count", "chat.operationProposal.recordDelete.todoCount"],
    [
      "review_material_count",
      "chat.operationProposal.recordDelete.reviewCount",
    ],
  ];
  for (const [key, labelKey] of countEntries) {
    const count = fieldNumber(snapshot, key);
    if (count !== null && count > 0) {
      countLabels.push(t(labelKey, { count }));
    }
  }
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.recordDelete.targetRecord")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {fieldString(snapshot, "title") ?? fieldString(snapshot, "record_id")}
        </dd>
      </div>
      {countLabels.length > 0 ? (
        <p className="text-label text-muted-foreground">
          {countLabels.join(" · ")}
        </p>
      ) : null}
      <p className="text-destructive text-label">
        {t("chat.operationProposal.recordDelete.hint")}
      </p>
    </>
  );
}

/** OP_COURSE_SOFT_DELETE 确认卡预览：目标课程、完整记录清单与计数、
 * 级联删除警告（Q8：批准后新增记录 → 旧批准失效重新预览）。 */
function CourseSoftDeletePreviewFields({ snapshot, t }: PreviewFieldsProps) {
  const rawRecords = snapshot?.records;
  const records = Array.isArray(rawRecords)
    ? rawRecords.filter(
        (item): item is Record<string, unknown> =>
          typeof item === "object" && item !== null,
      )
    : [];
  const recordCount = fieldNumber(snapshot, "record_count") ?? records.length;
  const titles = records
    .map((item) => fieldString(item, "title"))
    .filter((title): title is string => title !== null);
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.modify.targetCourse")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {fieldString(snapshot, "name") ?? fieldString(snapshot, "course_id")}
        </dd>
      </div>
      {recordCount > 0 ? (
        <p
          className="text-label text-muted-foreground focus-visible:ring-ring/40 max-h-40 overflow-y-auto break-words focus-visible:ring-3"
          tabIndex={0}
        >
          {t("chat.operationProposal.courseDelete.recordList", {
            count: recordCount,
            titles: titles.join("、"),
          })}
        </p>
      ) : null}
      <p className="text-destructive text-label">
        {t("chat.operationProposal.courseDelete.hint")}
      </p>
    </>
  );
}

/** OP_RECORD_MOVE_COURSE 确认卡预览：目标记录 + 课程 before/after
 * （原课程未归类＝收件箱占位；课程名经课程 API 按 id 拉取）。 */
function RecordMovePreviewFields({ payload, snapshot, t }: PreviewFieldsProps) {
  const afterCourseId = fieldString(payload, "target_course_id");
  const beforeCourseId = fieldString(snapshot, "course_id");
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.recordDelete.targetRecord")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {fieldString(snapshot, "title") ?? fieldString(snapshot, "record_id")}
        </dd>
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.recordMove.courseField")}
        </dt>
        <dd className="text-label text-ink-muted decoration-border-strong break-words line-through">
          {beforeCourseId ? (
            <TextRecordCourseName courseId={beforeCourseId} />
          ) : (
            t("chat.operationProposal.recordMove.inboxLabel")
          )}
        </dd>
        <ArrowRight
          className="text-ink-faint size-3 shrink-0"
          aria-hidden="true"
        />
        <dd className="text-label text-ink min-w-0 break-words">
          {afterCourseId ? (
            <TextRecordCourseName courseId={afterCourseId} />
          ) : null}
        </dd>
      </div>
      <p className="text-label text-muted-foreground">
        {t("chat.operationProposal.recordMove.hint")}
      </p>
    </>
  );
}

/** TEXT_RECORD_ADD 确认卡预览：目标课程 + 正文摘要 + 明示「保存后将尝试生成
 * AI 总结」（spec 用户故事 9）。 */
function TextRecordPreviewFields({ payload, t }: PreviewFieldsProps) {
  const targetCourseId = fieldString(payload, "course_id");
  const excerpt = contentExcerpt(payload.content);
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.textRecord.targetCourse")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {targetCourseId ? (
            <TextRecordCourseName courseId={targetCourseId} />
          ) : null}
        </dd>
      </div>
      {excerpt ? (
        <div className="flex gap-2">
          <dt className="text-label text-muted-foreground shrink-0">
            {t("chat.operationProposal.textRecord.content")}
          </dt>
          <dd className="text-label text-ink min-w-0 break-words">{excerpt}</dd>
        </div>
      ) : null}
      <p className="text-label text-muted-foreground">
        {t("chat.operationProposal.textRecord.confirmHint")}
      </p>
    </>
  );
}

/** COURSE_CREATE 回执行：课程入口跳转（/spaces 路由 validateSearch 必带 tab）。 */
function SettledCourseCreateRow({ status, result, t }: SettledRowProps) {
  const applied = status === "APPLIED";
  const courseId = fieldString(result, "course_id");
  return (
    <div className="bg-surface-subtle flex flex-col gap-1.5 rounded-md px-2.5 py-1.5">
      <p className="text-label text-muted-foreground">
        {t(
          applied
            ? "chat.operationProposal.accepted"
            : "chat.operationProposal.rejected",
        )}
      </p>
      {applied && courseId ? (
        <Link
          to="/spaces/$courseId"
          params={{ courseId }}
          search={{ tab: "overview" }}
          className="text-ink hover:bg-surface-raised text-label flex w-fit items-center gap-1 rounded px-1 py-0.5"
        >
          {t("chat.operationProposal.openCourse")}
          <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
      ) : null}
    </div>
  );
}

/** TEXT_RECORD_ADD 回执行：记录入口 + 总结任务真实状态（三态区分）。 */
function SettledTextRecordRow({ status, result, t }: SettledRowProps) {
  const applied = status === "APPLIED";
  const recordId = fieldString(result, "record_id");
  return (
    <div className="bg-surface-subtle flex flex-col gap-1.5 rounded-md px-2.5 py-1.5">
      <p className="text-label text-muted-foreground">
        {t(
          applied
            ? "chat.operationProposal.textRecord.accepted"
            : "chat.operationProposal.textRecord.rejected",
        )}
      </p>
      {applied ? (
        <p className="text-label text-muted-foreground">
          {summaryStateText(result, t)}
        </p>
      ) : null}
      {applied && recordId ? (
        <Link
          to="/records/$recordId"
          params={{ recordId }}
          className="text-ink hover:bg-surface-raised text-label flex w-fit items-center gap-1 rounded px-1 py-0.5"
        >
          {t("chat.operationProposal.textRecord.openRecord")}
          <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
      ) : null}
    </div>
  );
}

/** 修改 / 归档类回执行的共用骨架：结果文案 + 可选目标入口跳转。 */
function SettledActionRow({
  appliedTextKey,
  rejectedTextKey,
  openLabel,
  openTo,
  openParams,
  openSearch,
  status,
  t,
}: {
  appliedTextKey: string;
  rejectedTextKey: string;
  openLabel: string;
  openTo: string;
  openParams: Record<string, string>;
  openSearch?: Record<string, string>;
  status: AgentProposalOut["status"];
  t: TFunction;
}) {
  const applied = status === "APPLIED";
  return (
    <div className="bg-surface-subtle flex flex-col gap-1.5 rounded-md px-2.5 py-1.5">
      <p className="text-label text-muted-foreground">
        {t(applied ? appliedTextKey : rejectedTextKey)}
      </p>
      {applied ? (
        <Link
          to={openTo}
          params={openParams}
          search={openSearch}
          className="text-ink hover:bg-surface-raised text-label flex w-fit items-center gap-1 rounded px-1 py-0.5"
        >
          {openLabel}
          <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
      ) : null}
    </div>
  );
}

/** OP_COURSE_UPDATE 回执行：修改结果 + 课程入口跳转。 */
function SettledCourseUpdateRow({ status, result, t }: SettledRowProps) {
  const courseId = fieldString(result, "course_id");
  return (
    <SettledActionRow
      status={status}
      t={t}
      appliedTextKey="chat.operationProposal.courseUpdate.accepted"
      rejectedTextKey="chat.operationProposal.courseUpdate.rejected"
      openLabel={t("chat.operationProposal.openCourse")}
      openTo="/spaces/$courseId"
      openParams={courseId ? { courseId } : {}}
      openSearch={{ tab: "overview" }}
    />
  );
}

/** 课程归档 / 恢复回执行共用（文案键随动作传入）。 */
function SettledCourseStatusRow({
  status,
  result,
  t,
  appliedTextKey,
  rejectedTextKey,
}: SettledRowProps & { appliedTextKey: string; rejectedTextKey: string }) {
  const courseId = fieldString(result, "course_id");
  return (
    <SettledActionRow
      status={status}
      t={t}
      appliedTextKey={appliedTextKey}
      rejectedTextKey={rejectedTextKey}
      openLabel={t("chat.operationProposal.openCourse")}
      openTo="/spaces/$courseId"
      openParams={courseId ? { courseId } : {}}
      openSearch={{ tab: "overview" }}
    />
  );
}

/** 条目修改 / 归档 / 恢复回执行共用：结果 + 资料库条目入口。 */
function SettledLibraryItemRow({
  status,
  result,
  t,
  appliedTextKey,
  rejectedTextKey,
}: SettledRowProps & { appliedTextKey: string; rejectedTextKey: string }) {
  const itemId = fieldString(result, "item_id");
  return (
    <SettledActionRow
      status={status}
      t={t}
      appliedTextKey={appliedTextKey}
      rejectedTextKey={rejectedTextKey}
      openLabel={t("chat.operationProposal.libraryItemUpdate.openItem")}
      openTo="/library"
      openParams={{}}
      openSearch={itemId ? { sel: itemId, selType: "item" } : undefined}
    />
  );
}

/** 删除类回执行共用（工单 04）：结果文案（可带插值）+ 无目标入口
 * （目标已删除，无可跳转）。 */
function SettledDeletedRow({
  status,
  t,
  appliedTextKey,
  rejectedTextKey,
  appliedValues,
}: SettledRowProps & {
  appliedTextKey: string;
  rejectedTextKey: string;
  appliedValues?: Record<string, unknown>;
}) {
  const applied = status === "APPLIED";
  return (
    <div className="bg-surface-subtle flex flex-col gap-1.5 rounded-md px-2.5 py-1.5">
      <p className="text-label text-muted-foreground">
        {t(applied ? appliedTextKey : rejectedTextKey, appliedValues ?? {})}
      </p>
    </div>
  );
}

/** OP_RECORD_MOVE_COURSE 回执行：迁移结果 + 记录入口。 */
function SettledRecordMoveRow({ status, result, t }: SettledRowProps) {
  const recordId = fieldString(result, "record_id");
  return (
    <SettledActionRow
      status={status}
      t={t}
      appliedTextKey="chat.operationProposal.recordMove.accepted"
      rejectedTextKey="chat.operationProposal.recordMove.rejected"
      openLabel={t("chat.operationProposal.recordMove.openRecord")}
      openTo="/records/$recordId"
      openParams={recordId ? { recordId } : {}}
    />
  );
}

// ---------------------------------------------------------------------------
// 学习目标卡（通用 Agent 第三阶段工单 01）：goalFields 块承载共用字段标签
// 与目标类型枚举翻译，创建 / 更新两卡同源（先例：modify.targetCourse）。
// ---------------------------------------------------------------------------

/** 目标字段键集 = OP_GOAL_CREATE / OP_GOAL_UPDATE 共用的展示字段。 */
const GOAL_FIELD_LABEL_KEYS: Record<string, string> = {
  title: "chat.operationProposal.goalFields.title",
  target_date: "chat.operationProposal.goalFields.targetDate",
  daily_minutes: "chat.operationProposal.goalFields.dailyMinutes",
  target_score: "chat.operationProposal.goalFields.targetScore",
};

function goalFieldDisplay(
  key: string,
  value: unknown,
  t: TFunction,
): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (key === "daily_minutes") {
    return t("chat.operationProposal.goalFields.dailyMinutesValue", {
      count: Number(value),
    });
  }
  return excerpt(String(value));
}

/** OP_GOAL_CREATE 确认卡预览：目标课程（快照名）+ 类型 / 标题 / 期限 / 投入 / 分数。 */
function GoalCreatePreviewFields({ payload, snapshot, t }: PreviewFieldsProps) {
  const goalType = fieldString(payload, "goal_type");
  const rows: { label: string; value: string }[] = [
    {
      label: t("chat.operationProposal.goalFields.type"),
      value: goalType
        ? t(`chat.operationProposal.goalFields.goalType.${goalType}`)
        : "",
    },
    {
      label: t("chat.operationProposal.goalFields.title"),
      value: excerpt(fieldString(payload, "title") ?? "", 60) || "",
    },
  ];
  for (const key of ["target_date", "daily_minutes", "target_score"] as const) {
    const display = goalFieldDisplay(key, payload[key], t);
    if (display !== null) {
      rows.push({ label: t(GOAL_FIELD_LABEL_KEYS[key]), value: display });
    }
  }
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.goalFields.targetCourse")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {fieldString(snapshot, "name") ?? fieldString(payload, "course_id")}
        </dd>
      </div>
      {rows.map((row) => (
        <div key={row.label} className="flex gap-2">
          <dt className="text-label text-muted-foreground shrink-0">
            {row.label}
          </dt>
          <dd className="text-label text-ink min-w-0 break-words">
            {row.value}
          </dd>
        </div>
      ))}
      <p className="text-label text-muted-foreground">
        {t("chat.operationProposal.goalCreate.hint")}
      </p>
    </>
  );
}

/** OP_GOAL_UPDATE 确认卡预览：目标标题（快照）+ 修改字段 before/after + 状态流转行。 */
function GoalUpdatePreviewFields({ payload, snapshot, t }: PreviewFieldsProps) {
  const entries: { label: string; before: string | null; after: string }[] = [];
  for (const [key, labelKey] of Object.entries(GOAL_FIELD_LABEL_KEYS)) {
    const after = goalFieldDisplay(key, payload[key], t);
    if (after === null) continue;
    entries.push({
      label: t(labelKey),
      before: snapshot ? goalFieldDisplay(key, snapshot[key], t) : null,
      after,
    });
  }
  const status = fieldString(payload, "status");
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.goalUpdate.targetGoal")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {excerpt(fieldString(snapshot, "title") ?? "", 60) ||
            fieldString(payload, "goal_id")}
        </dd>
      </div>
      <BeforeAfterRows entries={entries} />
      {status ? (
        <div className="flex gap-2">
          <dt className="text-label text-muted-foreground shrink-0">
            {t("chat.operationProposal.goalUpdate.statusField")}
          </dt>
          <dd className="text-label text-ink min-w-0 break-words">
            {t(
              status === "COMPLETED"
                ? "chat.operationProposal.goalUpdate.statusCompleted"
                : "chat.operationProposal.goalUpdate.statusArchived",
            )}
          </dd>
        </div>
      ) : null}
      {status ? (
        <p className="text-label text-muted-foreground">
          {t("chat.operationProposal.goalUpdate.hint")}
        </p>
      ) : null}
    </>
  );
}

/** OP_GOAL_CREATE 回执行：结果文案 + 课程入口跳转（course_id 在结果投影里）。 */
function SettledGoalCreateRow({ status, result, t }: SettledRowProps) {
  const courseId = fieldString(result, "course_id");
  return (
    <SettledActionRow
      status={status}
      t={t}
      appliedTextKey="chat.operationProposal.goalCreate.accepted"
      rejectedTextKey="chat.operationProposal.goalCreate.rejected"
      openLabel={t("chat.operationProposal.openCourse")}
      openTo="/spaces/$courseId"
      openParams={courseId ? { courseId } : {}}
      openSearch={{ tab: "overview" }}
    />
  );
}

/** 纯文案回执行共用（工单 03）：结果两态文案随类型传入。 */
function SettledTextRow({
  appliedTextKey,
  rejectedTextKey,
  status,
  t,
}: SettledRowProps & { appliedTextKey: string; rejectedTextKey: string }) {
  return (
    <div className="bg-surface-subtle flex flex-col gap-1.5 rounded-md px-2.5 py-1.5">
      <p className="text-label text-muted-foreground">
        {t(status === "APPLIED" ? appliedTextKey : rejectedTextKey)}
      </p>
    </div>
  );
}

/** OP_GOAL_UPDATE 回执行：结果文案（目标暂无独立页面，计划 Tab 随后续工单接入）。 */
function SettledGoalUpdateRow(props: SettledRowProps) {
  return (
    <SettledTextRow
      {...props}
      appliedTextKey="chat.operationProposal.goalUpdate.accepted"
      rejectedTextKey="chat.operationProposal.goalUpdate.rejected"
    />
  );
}

/** 提案 payload / 快照的对象数组窄化（形状漂移时返回空数组兜底）。 */
function arrayField(
  source: Record<string, unknown> | null | undefined,
  key: string,
): Record<string, unknown>[] {
  const value = source?.[key];
  return Array.isArray(value)
    ? value.filter(
        (item): item is Record<string, unknown> =>
          typeof item === "object" && item !== null,
      )
    : [];
}

/** OP_PLAN_CONFIRM / OP_PLAN_REGENERATE 共用的阶段计划项渲染：排期概览 +
 * 分阶段计划项（日期 · 内容全文 · 时长 · 类型徽标 · 逐项理由——spec 用户故事
 * 10 要求理由可见；锁定项带保留标记）。 */
function PlanPhasesPreview({
  payload,
  snapshot,
  t,
  lockedBadge = false,
}: PreviewFieldsProps & { lockedBadge?: boolean }) {
  const phases = arrayField(payload, "phases");
  const items = phases.flatMap((phase) => arrayField(phase, "items"));
  const dates = items
    .map((item) => fieldString(item, "scheduled_date"))
    .filter((value): value is string => value !== null)
    .sort();
  const totalMinutes = items.reduce(
    (total, item) => total + (fieldNumber(item, "estimated_minutes") ?? 0),
    0,
  );
  return (
    <div className="flex w-full flex-col gap-1.5">
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        <span className="text-label text-ink min-w-0 font-medium break-words">
          {excerpt(fieldString(snapshot, "title") ?? "", 60) ||
            fieldString(payload, "goal_id")}
        </span>
        <span className="text-label text-muted-foreground">
          {fieldString(snapshot, "course_name") ?? ""}
        </span>
      </div>
      <p className="text-label text-muted-foreground">
        {dates.length > 0
          ? t("chat.operationProposal.planConfirm.scheduleSummary", {
              count: items.length,
              minutes: totalMinutes,
              from: dates[0],
              to: dates[dates.length - 1],
            })
          : t("chat.operationProposal.planConfirm.scheduleEmpty")}
      </p>
      {phases.map((phase, phaseIndex) => (
        <div key={phaseIndex} className="flex flex-col gap-1">
          <p className="text-label text-ink-muted font-medium">
            {excerpt(fieldString(phase, "title") ?? "", 40) ||
              t("chat.operationProposal.planConfirm.unnamedPhase")}
          </p>
          <ul className="flex flex-col gap-1">
            {arrayField(phase, "items").map((item, itemIndex) => {
              const itemType = fieldString(item, "action_type");
              const minutes = fieldNumber(item, "estimated_minutes");
              const reason = fieldString(item, "reason");
              const locked = item.user_locked === true;
              return (
                <li
                  key={itemIndex}
                  className="text-label text-ink-muted flex flex-col gap-0.5"
                >
                  <span className="flex flex-wrap items-baseline gap-x-1.5">
                    <span className="text-ink-faint tabular-nums">
                      {fieldString(item, "scheduled_date")?.slice(5) ?? ""}
                    </span>
                    <span className="min-w-0 break-words">
                      {fieldString(item, "content") ?? ""}
                    </span>
                    {minutes !== null ? (
                      <span className="text-ink-faint shrink-0">
                        {t("chat.operationProposal.planFields.minutesValue", {
                          count: minutes,
                        })}
                      </span>
                    ) : null}
                    {itemType !== null && isPlanItemType(itemType) ? (
                      <span className="text-ink-faint shrink-0">
                        {t(PLAN_ITEM_TYPE_KEYS[itemType])}
                      </span>
                    ) : null}
                    {lockedBadge && locked ? (
                      <span className="text-ink-faint shrink-0">
                        {t("chat.operationProposal.planRegenerate.lockedBadge")}
                      </span>
                    ) : null}
                  </span>
                  {reason !== null ? (
                    <span className="text-ink-faint break-words">
                      {t("chat.operationProposal.planFields.reasonLabel") +
                        reason}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** OP_PLAN_CONFIRM 确认卡预览（只读态：快照失效行回退渲染；可编辑态由
 * PlanDraftEditor 承载，工单 03）。 */
function PlanConfirmPreviewFields(props: PreviewFieldsProps) {
  const { t } = useTranslation();
  return (
    <div className="flex w-full flex-col gap-1.5">
      <PlanPhasesPreview {...props} />
      <p className="text-label text-muted-foreground">
        {t("chat.operationProposal.planConfirm.hint")}
      </p>
    </div>
  );
}

/** OP_PLAN_REGENERATE 确认卡预览（工单 03）：新版本全貌 + 锁定项保留标记。 */
function PlanRegeneratePreviewFields(props: PreviewFieldsProps) {
  const { t } = useTranslation();
  return (
    <div className="flex w-full flex-col gap-1.5">
      <PlanPhasesPreview {...props} lockedBadge />
      <p className="text-label text-muted-foreground">
        {t("chat.operationProposal.planRegenerate.hint")}
      </p>
    </div>
  );
}

/** 计划项字段展示值（OP_PLAN_ITEM_UPDATE before/after 行共用）。 */
function planItemFieldDisplay(
  key: string,
  value: unknown,
  t: TFunction,
): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (key === "estimated_minutes") {
    return t("chat.operationProposal.planFields.minutesValue", {
      count: Number(value),
    });
  }
  return excerpt(String(value));
}

const PLAN_ITEM_FIELD_LABEL_KEYS: Record<string, string> = {
  scheduled_date: "chat.operationProposal.planItemUpdate.dateField",
  estimated_minutes: "chat.operationProposal.planItemUpdate.minutesField",
  content: "chat.operationProposal.planItemUpdate.contentField",
};

/** OP_PLAN_ITEM_UPDATE 确认卡预览：目标计划项（快照内容）+ 修改字段
 * before/after（payload 非空字段 = 本次要改的字段，before 读执行前快照）。 */
function PlanItemUpdatePreviewFields({
  payload,
  snapshot,
  t,
}: PreviewFieldsProps) {
  const entries: { label: string; before: string | null; after: string }[] = [];
  for (const [key, labelKey] of Object.entries(PLAN_ITEM_FIELD_LABEL_KEYS)) {
    const after = planItemFieldDisplay(key, payload[key], t);
    if (after === null) continue;
    entries.push({
      label: t(labelKey),
      before: snapshot ? planItemFieldDisplay(key, snapshot[key], t) : null,
      after,
    });
  }
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.planItemUpdate.targetItem")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {excerpt(fieldString(snapshot, "content") ?? "") ||
            fieldString(payload, "item_id")}
        </dd>
      </div>
      <BeforeAfterRows entries={entries} />
      <p className="text-label text-muted-foreground">
        {t("chat.operationProposal.planItemUpdate.hint")}
      </p>
    </>
  );
}

/** OP_PLAN_ITEM_COMPLETE 确认卡预览：目标计划项 + 完成语义提示。 */
function PlanItemCompletePreviewFields({
  payload,
  snapshot,
  t,
}: PreviewFieldsProps) {
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.planItemComplete.targetItem")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {excerpt(fieldString(snapshot, "content") ?? "") ||
            fieldString(payload, "item_id")}
        </dd>
      </div>
      <p className="text-label text-muted-foreground">
        {t("chat.operationProposal.planItemComplete.hint")}
      </p>
    </>
  );
}

/** OP_SHARED_REF_ADD 确认卡预览：落点课程 + 被引用资料（快照）+ 只读边界提示。 */
function SharedRefAddPreviewFields({
  payload,
  snapshot,
  t,
}: PreviewFieldsProps) {
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.sharedRefAdd.targetCourse")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {excerpt(fieldString(snapshot, "course_name") ?? "") ||
            fieldString(payload, "course_id")}
        </dd>
      </div>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.sharedRefAdd.targetItem")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {excerpt(fieldString(snapshot, "item_title") ?? "") ||
            fieldString(payload, "library_item_id")}
        </dd>
      </div>
      <p className="text-label text-muted-foreground">
        {t("chat.operationProposal.sharedRefAdd.hint")}
      </p>
    </>
  );
}

/** OP_SHARED_REF_REMOVE 确认卡预览：目标课程 + 被移除引用的资料（快照，
 * 同一资料可被多空间引用——两行并列才能核对移除哪条关系）+ 原资料不动提示。 */
function SharedRefRemovePreviewFields({
  payload,
  snapshot,
  t,
}: PreviewFieldsProps) {
  return (
    <>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.sharedRefRemove.targetCourse")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {excerpt(fieldString(snapshot, "course_name") ?? "") ||
            fieldString(payload, "course_id")}
        </dd>
      </div>
      <div className="flex gap-2">
        <dt className="text-label text-muted-foreground shrink-0">
          {t("chat.operationProposal.sharedRefRemove.targetItem")}
        </dt>
        <dd className="text-label text-ink min-w-0 break-words">
          {excerpt(fieldString(snapshot, "item_title") ?? "") ||
            fieldString(payload, "library_item_id")}
        </dd>
      </div>
      <p className="text-label text-muted-foreground">
        {t("chat.operationProposal.sharedRefRemove.hint")}
      </p>
    </>
  );
}

/** OP_PLAN_CONFIRM 回执行：结果文案（版本 / 项数）+ 课程入口（计划 Tab 随工单 04）。 */
function SettledPlanConfirmRow({ status, result, t }: SettledRowProps) {
  if (status !== "APPLIED") {
    return (
      <div className="bg-surface-subtle rounded-md px-2.5 py-1.5">
        <p className="text-label text-muted-foreground">
          {t("chat.operationProposal.planConfirm.rejected")}
        </p>
      </div>
    );
  }
  const courseId = fieldString(result, "course_id");
  const version = fieldNumber(result, "plan_version");
  const count = fieldNumber(result, "item_count");
  return (
    <div className="bg-surface-subtle flex flex-col gap-1.5 rounded-md px-2.5 py-1.5">
      <p className="text-label text-muted-foreground">
        {version !== null && count !== null
          ? t("chat.operationProposal.planConfirm.accepted", {
              version,
              count,
            })
          : t("chat.operationProposal.planConfirm.acceptedFallback")}
      </p>
      {courseId ? (
        <Link
          to="/spaces/$courseId"
          params={{ courseId }}
          search={{ tab: "overview" }}
          className="text-ink hover:bg-surface-raised text-label flex w-fit items-center gap-1 rounded px-1 py-0.5"
        >
          <ArrowRight data-icon="inline-start" aria-hidden="true" />
          {t("chat.operationProposal.openCourse")}
        </Link>
      ) : null}
    </div>
  );
}

/** 类型专属卡片行为表（键 = 提案类型；涵盖类型即本卡过滤集合）。 */
type OperationCardSpec = {
  /** 跨类型共用文案键（failed/failedDetail/accept/reject）的类型前缀。 */
  label: (key: string) => string;
  /** 确认卡预览字段行（dl 内）。 */
  PreviewFields: ComponentType<PreviewFieldsProps>;
  /** APPLIED/REJECTED 回执行。 */
  SettledRow: ComponentType<SettledRowProps>;
  /** 第三动作「重新生成」（可选）：按载荷构造代发指令消息，null = 不渲染按钮。 */
  regenerateMessage?: (payload: Record<string, unknown>) => string | null;
  /** 可编辑草案（可选，工单 03）：待确认行渲染编辑器替代只读预览，确认时
   * 携带编辑后载荷（服务端校验边界）。 */
  DraftEditor?: ComponentType<DraftEditorProps>;
};

const CARD_BY_TYPE: Record<string, OperationCardSpec> = {
  COURSE_CREATE: {
    label: (key) => `chat.operationProposal.${key}`,
    PreviewFields: CourseCreatePreviewFields,
    SettledRow: SettledCourseCreateRow,
  },
  TEXT_RECORD_ADD: {
    label: (key) => `chat.operationProposal.textRecord.${key}`,
    PreviewFields: TextRecordPreviewFields,
    SettledRow: SettledTextRecordRow,
  },
  OP_COURSE_UPDATE: {
    label: (key) => `chat.operationProposal.courseUpdate.${key}`,
    PreviewFields: CourseUpdatePreviewFields,
    SettledRow: SettledCourseUpdateRow,
  },
  OP_COURSE_ARCHIVE: {
    label: (key) => `chat.operationProposal.courseArchive.${key}`,
    PreviewFields: CourseArchivePreviewFields,
    SettledRow: (props) => (
      <SettledCourseStatusRow
        {...props}
        appliedTextKey="chat.operationProposal.courseArchive.accepted"
        rejectedTextKey="chat.operationProposal.courseArchive.rejected"
      />
    ),
  },
  OP_COURSE_RESTORE: {
    label: (key) => `chat.operationProposal.courseRestore.${key}`,
    PreviewFields: CourseRestorePreviewFields,
    SettledRow: (props) => (
      <SettledCourseStatusRow
        {...props}
        appliedTextKey="chat.operationProposal.courseRestore.accepted"
        rejectedTextKey="chat.operationProposal.courseRestore.rejected"
      />
    ),
  },
  OP_LIBRARY_ITEM_UPDATE: {
    label: (key) => `chat.operationProposal.libraryItemUpdate.${key}`,
    PreviewFields: LibraryItemUpdatePreviewFields,
    SettledRow: (props) => (
      <SettledLibraryItemRow
        {...props}
        appliedTextKey="chat.operationProposal.libraryItemUpdate.accepted"
        rejectedTextKey="chat.operationProposal.libraryItemUpdate.rejected"
      />
    ),
  },
  OP_LIBRARY_ITEM_ARCHIVE: {
    label: (key) => `chat.operationProposal.libraryItemArchive.${key}`,
    PreviewFields: LibraryItemArchivePreviewFields,
    SettledRow: (props) => (
      <SettledLibraryItemRow
        {...props}
        appliedTextKey="chat.operationProposal.libraryItemArchive.accepted"
        rejectedTextKey="chat.operationProposal.libraryItemArchive.rejected"
      />
    ),
  },
  OP_LIBRARY_ITEM_RESTORE: {
    label: (key) => `chat.operationProposal.libraryItemRestore.${key}`,
    PreviewFields: LibraryItemRestorePreviewFields,
    SettledRow: (props) => (
      <SettledLibraryItemRow
        {...props}
        appliedTextKey="chat.operationProposal.libraryItemRestore.accepted"
        rejectedTextKey="chat.operationProposal.libraryItemRestore.rejected"
      />
    ),
  },
  OP_RECORD_SOFT_DELETE: {
    label: (key) => `chat.operationProposal.recordDelete.${key}`,
    PreviewFields: RecordSoftDeletePreviewFields,
    SettledRow: (props) => (
      <SettledDeletedRow
        {...props}
        appliedTextKey="chat.operationProposal.recordDelete.accepted"
        rejectedTextKey="chat.operationProposal.recordDelete.rejected"
      />
    ),
  },
  OP_COURSE_SOFT_DELETE: {
    label: (key) => `chat.operationProposal.courseDelete.${key}`,
    PreviewFields: CourseSoftDeletePreviewFields,
    SettledRow: ({ status, result, t }) => (
      <SettledDeletedRow
        status={status}
        result={result}
        t={t}
        appliedTextKey="chat.operationProposal.courseDelete.accepted"
        rejectedTextKey="chat.operationProposal.courseDelete.rejected"
        appliedValues={{
          count: fieldNumber(result, "record_count") ?? 0,
        }}
      />
    ),
  },
  OP_RECORD_MOVE_COURSE: {
    label: (key) => `chat.operationProposal.recordMove.${key}`,
    PreviewFields: RecordMovePreviewFields,
    SettledRow: SettledRecordMoveRow,
  },
  OP_GOAL_CREATE: {
    label: (key) => `chat.operationProposal.goalCreate.${key}`,
    PreviewFields: GoalCreatePreviewFields,
    SettledRow: SettledGoalCreateRow,
  },
  OP_GOAL_UPDATE: {
    label: (key) => `chat.operationProposal.goalUpdate.${key}`,
    PreviewFields: GoalUpdatePreviewFields,
    SettledRow: SettledGoalUpdateRow,
  },
  OP_PLAN_CONFIRM: {
    label: (key) => `chat.operationProposal.planConfirm.${key}`,
    PreviewFields: PlanConfirmPreviewFields,
    SettledRow: SettledPlanConfirmRow,
    // 重新生成入口（spec 工单 02 三动作）：放弃旧草案 + 代发指令让 Agent 重排。
    regenerateMessage: (payload) => {
      const goalId = fieldString(payload, "goal_id");
      return goalId !== null
        ? `请基于课程资料为目标 ${goalId} 重新生成一份学习计划草案`
        : null;
    },
    // 确认卡可编辑（工单 03，spec 用户故事 9）：改日期 / 时长 / 删项 / 排序。
    DraftEditor: PlanDraftEditor,
  },
  OP_PLAN_ITEM_UPDATE: {
    label: (key) => `chat.operationProposal.planItemUpdate.${key}`,
    PreviewFields: PlanItemUpdatePreviewFields,
    SettledRow: (props) => (
      <SettledTextRow
        {...props}
        appliedTextKey="chat.operationProposal.planItemUpdate.accepted"
        rejectedTextKey="chat.operationProposal.planItemUpdate.rejected"
      />
    ),
  },
  OP_PLAN_ITEM_COMPLETE: {
    label: (key) => `chat.operationProposal.planItemComplete.${key}`,
    PreviewFields: PlanItemCompletePreviewFields,
    SettledRow: (props) => (
      <SettledTextRow
        {...props}
        appliedTextKey="chat.operationProposal.planItemComplete.accepted"
        rejectedTextKey="chat.operationProposal.planItemComplete.rejected"
      />
    ),
  },
  OP_PLAN_REGENERATE: {
    label: (key) => `chat.operationProposal.planRegenerate.${key}`,
    PreviewFields: PlanRegeneratePreviewFields,
    SettledRow: SettledPlanConfirmRow,
  },
  OP_SHARED_REF_ADD: {
    label: (key) => `chat.operationProposal.sharedRefAdd.${key}`,
    PreviewFields: SharedRefAddPreviewFields,
    SettledRow: (props) => (
      <SettledTextRow
        {...props}
        appliedTextKey="chat.operationProposal.sharedRefAdd.accepted"
        rejectedTextKey="chat.operationProposal.sharedRefAdd.rejected"
      />
    ),
  },
  OP_SHARED_REF_REMOVE: {
    label: (key) => `chat.operationProposal.sharedRefRemove.${key}`,
    PreviewFields: SharedRefRemovePreviewFields,
    SettledRow: (props) => (
      <SettledTextRow
        {...props}
        appliedTextKey="chat.operationProposal.sharedRefRemove.accepted"
        rejectedTextKey="chat.operationProposal.sharedRefRemove.rejected"
      />
    ),
  },
  OP_UNDO: {
    label: (key) => `chat.operationProposal.undo.${key}`,
    PreviewFields: UndoPreviewFields,
    SettledRow: SettledUndoRow,
  },
};

/** 本卡涵盖的操作提案类型（02 课程创建 / 03 文本记录 / 03' 修改与归档）＝配置表键。 */
const OPERATION_PROPOSAL_TYPES = new Set(Object.keys(CARD_BY_TYPE));

/** 共享引用提案类型：确认 / 拒绝后须失效共享引用缓存（清单与候选）。 */
const SHARED_REF_PROPOSAL_TYPES = new Set([
  "OP_SHARED_REF_ADD",
  "OP_SHARED_REF_REMOVE",
]);

/** 操作卡文案键：查类型配置表（共用键的类型前缀分派，03 review 收敛单点）。 */
function labelKey(proposal: AgentProposalOut, key: string): string {
  // proposals 已按 OPERATION_PROPOSAL_TYPES（= 表键）过滤，查表恒命中。
  return CARD_BY_TYPE[proposal.proposal_type].label(key);
}

/** 提案回执行的撤销入口（工单 06 补充：确认路径的消息流撤销）。
 *
 * 依据＝确认事务内回写的 operation 行（proposal_id 关联）：成功且可撤销且
 * 未撤销 → 「撤销」按钮；已撤销 → 标记（补偿行不进本卡，标记经 undone_by
 * 派生）；不可撤销 → 就地呈现原因（spec 用户故事 28，与直执行回执卡/操作
 * 历史同口径）；REJECTED / 无关联行（历史数据、查询缺席）不渲染——入口
 * 仍可在设置 → 操作历史找到。 */
function ProposalUndoEntry({
  operation,
  pending,
  error,
  onUndo,
}: {
  operation: AgentOperationOut | null;
  pending: boolean;
  error: string | null;
  onUndo: (operationId: string) => void;
}) {
  const { t } = useTranslation();
  if (operation === null || operation.status !== "SUCCEEDED") {
    return null;
  }
  if (operation.undone_by !== null) {
    return (
      <span className="text-label text-muted-foreground shrink-0">
        {t("chat.executedOperation.undone")}
      </span>
    );
  }
  if (!operation.undoable) {
    // 创建类等不可撤销动作：不渲染按钮（spec 决策 19 首批范围），原因如实
    // 呈现（undo_reason 缺省的防御行除外）。
    if (operation.undo_reason === null) {
      return null;
    }
    return (
      <p className="text-label text-muted-foreground w-full">
        {t("chat.executedOperation.notUndoable", {
          reason: operation.undo_reason,
        })}
      </p>
    );
  }
  return (
    <div className="flex shrink-0 flex-col items-end gap-1">
      <Button
        size="xs"
        variant="ghost"
        disabled={pending}
        onClick={() => onUndo(operation.id)}
      >
        <Undo2 data-icon="inline-start" aria-hidden="true" />
        {t("chat.executedOperation.undo")}
      </Button>
      {error ? (
        <p role="alert" className="text-destructive text-label">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** 待确认/FAILED 行：快照失效只能重新提案，其余失败可重试；声明可编辑草案的
 * 类型（工单 03）渲染编辑器，确认时携带编辑后载荷。 */
function ActionableProposalRow({
  proposal,
  status,
  busy,
  onDecide,
  onRegenerate,
  t,
}: {
  proposal: AgentProposalOut;
  status: AgentProposalOut["status"];
  busy: boolean;
  onDecide: (
    proposalId: string,
    accept: boolean,
    editedPayload?: Record<string, unknown>,
  ) => void;
  /** 重新生成（可选，类型配置声明第三动作时传入）：放弃本草案 + 代发指令。 */
  onRegenerate?: (proposalId: string, message: string) => void;
  t: TFunction;
}) {
  const reason = proposal.error_code
    ? t(`errors.${proposal.error_code}`, proposal.error_code)
    : null;
  const snapshotStale =
    status === "FAILED" && proposal.error_code === "OPERATION_SNAPSHOT_STALE";
  const spec = CARD_BY_TYPE[proposal.proposal_type];
  const PreviewFields = spec.PreviewFields;
  const DraftEditor = spec.DraftEditor;
  // 编辑态（null = 未编辑，确认时发原载荷）：行按 proposal.id key 隔离。
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const draftEmpty =
    draft !== null && planDraftItemCount(draft) === 0 && !snapshotStale;
  const regenerateMessage =
    onRegenerate !== undefined && spec.regenerateMessage !== undefined
      ? spec.regenerateMessage(proposal.payload ?? {})
      : null;
  return (
    <li className="bg-surface-subtle flex flex-wrap items-center gap-2 rounded-md px-2.5 py-1.5">
      {status === "FAILED" ? (
        <p role="alert" className="text-destructive text-label w-full">
          {snapshotStale
            ? `${t(labelKey(proposal, "failed"))} ${reason}`
            : reason
              ? t(labelKey(proposal, "failedDetail"), { reason })
              : t(labelKey(proposal, "failed"))}
        </p>
      ) : null}
      {DraftEditor !== undefined && !snapshotStale ? (
        <div className="min-w-0 flex-1">
          <DraftEditor
            payload={draft ?? proposal.payload ?? {}}
            snapshot={proposal.snapshot ?? null}
            onChange={setDraft}
            t={t}
          />
        </div>
      ) : (
        <dl className="min-w-0 flex-1">
          <PreviewFields
            payload={proposal.payload ?? {}}
            snapshot={proposal.snapshot ?? null}
            t={t}
          />
        </dl>
      )}
      {!snapshotStale ? (
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label={t(labelKey(proposal, "accept"))}
          disabled={busy || draftEmpty}
          onClick={() => onDecide(proposal.id, true, draft ?? undefined)}
        >
          <Check className="size-3.5" aria-hidden="true" />
        </Button>
      ) : null}
      <Button
        variant="ghost"
        size="icon-xs"
        aria-label={t(labelKey(proposal, "reject"))}
        disabled={busy}
        onClick={() => onDecide(proposal.id, false)}
      >
        <X className="size-3.5" aria-hidden="true" />
      </Button>
      {regenerateMessage !== null ? (
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label={t(labelKey(proposal, "regenerate"))}
          disabled={busy}
          onClick={() => onRegenerate?.(proposal.id, regenerateMessage)}
        >
          <RefreshCw className="size-3.5" aria-hidden="true" />
        </Button>
      ) : null}
    </li>
  );
}

/** 消息流内的操作提案就地确认卡（通用 Agent 第一阶段工单 02/03）：
 * 模型经写工具创建的 COURSE_CREATE / TEXT_RECORD_ADD 提案，完整参数预览后确认
 * （真实执行）或拒绝（零业务事实）；APPLIED 后转回执态——课程创建提供课程
 * 入口跳转，文本记录提供记录入口 + 总结任务真实状态（已提交 ≠ 未触发 ≠ 提交
 * 失败，spec 决策 15）。提案本体唯一事实源是服务端（agent_proposals 表）：
 * 断线/重启经本会话全状态提案查询恢复状态视图（工单 02 review）——APPLIED 的
 * 回执、FAILED 的失败原因与可用操作、REJECTED 的终态文案均由查询还原，不依赖组件内存。 */
export function ChatOperationProposalCard({
  sessionId,
  onSendMessage,
}: ChatOperationProposalCardProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [overrides, setOverrides] = useState<Record<string, DecisionOverride>>(
    {},
  );
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 本会话全状态提案（后端 session_id 过滤，工单 02 review）。
  // staleTime 0 + key 含会话：重启、切回会话、断线后重进一律挂载即拉最新。
  const { data: sessionProposals } = useQuery({
    queryKey: libraryKeys.sessionProposals(sessionId),
    queryFn: () => libraryApi.listProposals({ session_id: sessionId }),
    staleTime: 0,
  });

  // 确认路径回写的 operation 行（proposal_id 关联，工单 06 补充：提案回执行的
  // 撤销入口）。与直执行回执卡共用同一查询键（缓存一致，撤销后一次失效双卡同步）。
  const { data: sessionOperations } = useQuery({
    queryKey: agentKeys.sessionOperations(sessionId),
    queryFn: () =>
      operationHistoryApi.listOperations({ session_id: sessionId, limit: 200 }),
    staleTime: 0,
  });
  const operationByProposal = useMemo(() => {
    const map = new Map<string, AgentOperationOut>();
    for (const operation of sessionOperations ?? []) {
      if (operation.proposal_id !== null) {
        map.set(operation.proposal_id, operation);
      }
    }
    return map;
  }, [sessionOperations]);

  // 撤销是 UI 显式动作＝用户授权（工单 06）：沿用直执行回执卡同一模式。
  const undo = useMutation({
    mutationFn: (operationId: string) =>
      operationHistoryApi.undoOperation(operationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: agentKeys.sessionOperations(sessionId),
      });
      // 撤销可能还原共享引用（补偿动作跨闭包不可知类型）：统一失效引用缓存
      //（低频显式动作，代价仅挂载中查询一次重取）。
      void queryClient.invalidateQueries({ queryKey: sharedRefsKeys.all });
    },
  });

  const proposals = useMemo(
    () =>
      (sessionProposals ?? []).filter(
        (proposal: AgentProposalOut) =>
          OPERATION_PROPOSAL_TYPES.has(proposal.proposal_type) &&
          proposal.session_id === sessionId,
      ),
    [sessionProposals, sessionId],
  );

  if (proposals.length === 0) {
    return null;
  }
  const statusOf = (proposal: AgentProposalOut): AgentProposalOut["status"] =>
    overrides[proposal.id]?.status ?? proposal.status;
  const resultOf = (
    proposal: AgentProposalOut,
  ): Record<string, unknown> | null =>
    overrides[proposal.id]?.result ?? proposal.result ?? null;
  const settled = proposals.filter(
    (proposal) =>
      statusOf(proposal) === "APPLIED" || statusOf(proposal) === "REJECTED",
  );
  // FAILED 保留失败原因；快照失效由行组件隐藏同一提案的确认按钮。
  const actionable = proposals.filter(
    (proposal) =>
      statusOf(proposal) === "PENDING" || statusOf(proposal) === "FAILED",
  );

  const decide = (
    proposalId: string,
    accept: boolean,
    editedPayload?: Record<string, unknown>,
  ) => {
    setBusyId(proposalId);
    setError(null);
    const request: Promise<AgentProposalOut> = accept
      ? libraryApi.confirmProposal(proposalId, editedPayload)
      : libraryApi.rejectProposal(proposalId);
    request
      .then((result) => {
        setOverrides((current) => ({
          ...current,
          [proposalId]: {
            status: result.status === "APPLIED" ? "APPLIED" : "REJECTED",
            result: result.result ?? null,
          },
        }));
        void queryClient.invalidateQueries({
          queryKey: [...libraryKeys.all, "proposals"],
        });
        // 共享引用提案确认 / 拒绝：失效引用缓存（清单与候选，desktop-state.md
        // 「相关列表/聚合 key」——staleTime 60s 内不会自愈）。
        const proposal = proposals.find((item) => item.id === proposalId);
        if (
          proposal !== undefined &&
          SHARED_REF_PROPOSAL_TYPES.has(proposal.proposal_type)
        ) {
          void queryClient.invalidateQueries({
            queryKey: sharedRefsKeys.all,
          });
        }
      })
      .catch((exc: unknown) => {
        setError(exc instanceof Error ? exc.message : String(exc));
        // 确认超时/失败后回查真相（工单 02 review）：请求可能已实际应用
        // （回执经查询还原），或已落 FAILED（失败原因 + 可用操作）。
        void queryClient.invalidateQueries({
          queryKey: libraryKeys.sessionProposals(sessionId),
        });
      })
      .finally(() => setBusyId(null));
  };

  // 重新生成（类型配置声明第三动作时可用）：旧草案先落 REJECTED 终态失效
  // （零业务写入、回执如实呈现「已放弃」），再代发指令让 Agent 重排一份。
  const regenerate = (proposalId: string, message: string) => {
    setBusyId(proposalId);
    setError(null);
    libraryApi
      .rejectProposal(proposalId)
      .then(() => {
        setOverrides((current) => ({
          ...current,
          [proposalId]: { status: "REJECTED", result: null },
        }));
        void queryClient.invalidateQueries({
          queryKey: [...libraryKeys.all, "proposals"],
        });
        onSendMessage?.(message);
      })
      .catch((exc: unknown) => {
        setError(exc instanceof Error ? exc.message : String(exc));
        void queryClient.invalidateQueries({
          queryKey: libraryKeys.sessionProposals(sessionId),
        });
      })
      .finally(() => setBusyId(null));
  };

  return (
    <section
      aria-label={t("chat.operationProposal.panelTitle")}
      className="border-border/60 mt-2 flex flex-col gap-2 rounded-md border px-3 py-2"
    >
      <p className="text-label text-muted-foreground">
        {t("chat.operationProposal.panelTitle")}
      </p>
      {settled.map((proposal) => {
        const SettledRow = CARD_BY_TYPE[proposal.proposal_type].SettledRow;
        const operation = operationByProposal.get(proposal.id) ?? null;
        return (
          <div key={proposal.id} className="flex flex-wrap items-center gap-2">
            <div className="min-w-0 flex-1">
              <SettledRow
                status={statusOf(proposal)}
                result={resultOf(proposal)}
                t={t}
              />
            </div>
            <ProposalUndoEntry
              operation={operation}
              pending={undo.isPending}
              error={
                undo.isError &&
                operation !== null &&
                undo.variables === operation.id
                  ? undo.error.message
                  : null
              }
              onUndo={(operationId) => undo.mutate(operationId)}
            />
          </div>
        );
      })}
      <ul className="flex flex-col gap-1.5">
        {actionable.map((proposal) => (
          <ActionableProposalRow
            key={proposal.id}
            proposal={proposal}
            status={statusOf(proposal)}
            busy={busyId !== null}
            onDecide={decide}
            onRegenerate={onSendMessage !== undefined ? regenerate : undefined}
            t={t}
          />
        ))}
      </ul>
      {error ? (
        <p role="alert" className="text-destructive text-label">
          {error}
        </p>
      ) : null}
    </section>
  );
}
