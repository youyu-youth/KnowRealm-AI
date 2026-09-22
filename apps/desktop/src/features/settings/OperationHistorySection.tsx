import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, Trash2 } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { settingsKeys } from "@/features/settings/api/keys";
import {
  operationHistoryApi,
  type AgentOperationOut,
} from "@/features/settings/api/operationHistory";
import {
  SettingsPanelHeader,
  SettingsRow,
} from "@/features/settings/SettingsLayout";

/** 全部选项的哨兵值（后端无此状态；选中时不带 status 查询参数）。 */
const ALL_OPTION = "ALL";

const RUN_STATUS_OPTIONS = [
  "RUNNING",
  "WAITING_USER",
  "COMPLETED",
  "PARTIAL_COMPLETED",
  "FAILED",
  "CANCELLED",
] as const;

const OPERATION_STATUS_OPTIONS = [
  "PLANNED",
  "SUCCEEDED",
  "FAILED",
  "SKIPPED",
  "CANCELLED",
] as const;

type StatusFilterProps = {
  filter: string;
  onFilterChange: (value: string) => void;
  options: readonly string[];
  optionLabel: (value: string) => string;
};

/** 状态过滤下拉（任务 / 单步操作两处复用；ALL=不带 status 参数）。 */
function StatusFilterSelect({
  filter,
  onFilterChange,
  options,
  optionLabel,
}: StatusFilterProps) {
  const { t } = useTranslation();
  const items = [ALL_OPTION, ...options].map((value) => ({
    value,
    label:
      value === ALL_OPTION
        ? t("settings.operationHistory.filter.all")
        : optionLabel(value),
  }));
  return (
    <Select
      items={items}
      value={filter}
      onValueChange={(value) => {
        if (value !== null) onFilterChange(value);
      }}
    >
      <SelectTrigger
        className="bg-background h-9 w-44 rounded-lg"
        aria-label={t("settings.operationHistory.filterLabel")}
      >
        <SelectValue>
          {filter === ALL_OPTION
            ? t("settings.operationHistory.filter.all")
            : optionLabel(filter)}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}

/** 操作状态 → 展示色（成功=强调绿语义、失败=警示红、未决/跳过=中性）。 */
function statusTone(status: string): string {
  if (status === "SUCCEEDED" || status === "COMPLETED") {
    return "text-success-foreground";
  }
  if (status === "FAILED") {
    return "text-destructive";
  }
  return "text-muted-foreground";
}

/** 操作历史分区（通用 Agent 第二阶段工单 01）：任务（run）列表展开逐操作、
 * 单步操作条目、模式切换审计与显式清理。Run 推进与模式切换写入随 02/05 票
 * 接入——本阶段 runs / activity 恒空态，操作条目由第一阶段两类动作确认回写。 */
export function OperationHistorySection() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [purgeOpen, setPurgeOpen] = useState(false);
  const [runFilter, setRunFilter] = useState<string>(ALL_OPTION);
  const [operationFilter, setOperationFilter] = useState<string>(ALL_OPTION);

  const invalidateHistory = () => {
    void queryClient.invalidateQueries({
      queryKey: ["settings", "operation-runs"],
    });
    void queryClient.invalidateQueries({
      queryKey: settingsKeys.operations,
    });
  };

  const purge = useMutation({
    mutationFn: () => operationHistoryApi.purgeFinished(),
    onSuccess: () => {
      invalidateHistory();
      purge.reset();
      setPurgeOpen(false);
    },
  });

  return (
    <section
      aria-labelledby="settings-operation-history-title"
      className="max-w-5xl"
    >
      <SettingsPanelHeader
        id="settings-operation-history-title"
        title={t("settings.operationHistory.title")}
      />
      <p className="text-body text-muted-foreground max-w-reading mt-2">
        {t("settings.operationHistory.description")}
      </p>
      <div className="mt-8 flex flex-col gap-8">
        <RunsBlock filter={runFilter} onFilterChange={setRunFilter} />
        <OperationsBlock
          filter={operationFilter}
          onFilterChange={setOperationFilter}
        />
        <ActivityBlock />
      </div>

      <div className="mt-8 flex justify-end">
        <Button
          variant="outline"
          disabled={purge.isPending}
          onClick={() => setPurgeOpen(true)}
        >
          {purge.isPending ? (
            <Spinner
              data-icon="inline-start"
              aria-label={t("settings.operationHistory.purge.pending")}
            />
          ) : (
            <Trash2 data-icon="inline-start" aria-hidden="true" />
          )}
          {t("settings.operationHistory.purge.button")}
        </Button>
      </div>

      <Dialog open={purgeOpen} onOpenChange={setPurgeOpen}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>
              {t("settings.operationHistory.purge.title")}
            </DialogTitle>
            <DialogDescription>
              {t("settings.operationHistory.purge.description")}
            </DialogDescription>
          </DialogHeader>
          {purge.isError ? (
            <Alert variant="destructive">
              <AlertDescription>{purge.error.message}</AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>
              {t("settings.operationHistory.purge.cancel")}
            </DialogClose>
            <Button
              variant="destructive"
              disabled={purge.isPending}
              onClick={() => purge.mutate()}
            >
              {t("settings.operationHistory.purge.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

/** 任务（run）列表：状态过滤 + 展开逐操作 + 单任务历史删除（终态守卫在后端）。 */
function RunsBlock({
  filter,
  onFilterChange,
}: {
  filter: string;
  onFilterChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const runs = useQuery({
    queryKey: [...settingsKeys.operationRuns, filter],
    queryFn: () =>
      operationHistoryApi.listRuns(
        filter === ALL_OPTION ? {} : { status: filter },
      ),
  });

  const removeRun = useMutation({
    mutationFn: (runId: string) => operationHistoryApi.deleteRun(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["settings", "operation-runs"],
      });
    },
  });

  return (
    <SettingsRow
      label={t("settings.operationHistory.runsLabel")}
      description={t("settings.operationHistory.runsHint")}
    >
      <div className="max-w-reading flex flex-col gap-3">
        <StatusFilterSelect
          filter={filter}
          onFilterChange={onFilterChange}
          options={RUN_STATUS_OPTIONS}
          optionLabel={(value) =>
            t(`settings.operationHistory.runStatus.${value}`)
          }
        />

        {runs.isPending ? (
          <p role="status" className="text-label text-muted-foreground">
            <Spinner aria-hidden="true" />{" "}
            {t("settings.operationHistory.loading")}
          </p>
        ) : runs.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{runs.error.message}</AlertDescription>
          </Alert>
        ) : runs.data.length === 0 ? (
          <p className="text-label text-muted-foreground">
            {t("settings.operationHistory.runsEmpty")}
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {runs.data.map((run) => (
              <li key={run.id} className="bg-surface-subtle rounded-md">
                <div className="flex items-center gap-2 px-2.5 py-1.5">
                  <button
                    type="button"
                    className="hover:bg-surface-raised flex items-center gap-2 rounded p-1"
                    aria-expanded={expandedId === run.id}
                    aria-label={t("settings.operationHistory.runToggle")}
                    onClick={() =>
                      setExpandedId(expandedId === run.id ? null : run.id)
                    }
                  >
                    {expandedId === run.id ? (
                      <ChevronDown className="size-3.5" aria-hidden />
                    ) : (
                      <ChevronRight className="size-3.5" aria-hidden />
                    )}
                  </button>
                  <span
                    className={`text-label font-label min-w-24 ${statusTone(run.status)}`}
                  >
                    {t(`settings.operationHistory.runStatus.${run.status}`)}
                  </span>
                  <span className="text-label text-muted-foreground min-w-0 flex-1 truncate">
                    {run.instruction_text ??
                      t("settings.operationHistory.runUntitled")}
                  </span>
                  <span className="text-label text-muted-foreground shrink-0">
                    {formatTime(run.created_at)}
                  </span>
                  <button
                    type="button"
                    className="hover:bg-surface-raised rounded p-1"
                    aria-label={t("settings.operationHistory.runDelete")}
                    disabled={removeRun.isPending}
                    onClick={() => removeRun.mutate(run.id)}
                  >
                    <Trash2 className="size-3.5" aria-hidden />
                  </button>
                </div>
                {expandedId === run.id ? <RunDetail runId={run.id} /> : null}
              </li>
            ))}
          </ul>
        )}
        {removeRun.isError ? (
          <p role="alert" className="text-destructive text-label">
            {removeRun.error.message}
          </p>
        ) : null}
      </div>
    </SettingsRow>
  );
}

/** 展开的任务详情：逐操作行（复用单步操作行组件）。 */
function RunDetail({ runId }: { runId: string }) {
  const { t } = useTranslation();
  const detail = useQuery({
    queryKey: settingsKeys.operationRunDetail(runId),
    queryFn: () => operationHistoryApi.getRun(runId),
  });

  if (detail.isPending) {
    return (
      <p role="status" className="text-label text-muted-foreground px-8 py-2">
        <Spinner aria-hidden="true" /> {t("settings.operationHistory.loading")}
      </p>
    );
  }
  if (detail.isError) {
    return (
      <p role="alert" className="text-destructive text-label px-8 py-2">
        {detail.error.message}
      </p>
    );
  }
  if (detail.data.operations.length === 0) {
    return (
      <p className="text-label text-muted-foreground px-8 py-2">
        {t("settings.operationHistory.runOperationsEmpty")}
      </p>
    );
  }
  return (
    <ul className="border-border/60 flex flex-col gap-1 border-t px-6 py-2">
      {detail.data.operations.map((operation) => (
        <OperationRow key={operation.id} operation={operation} />
      ))}
    </ul>
  );
}

/** 单步操作列表（第一阶段两类动作确认回写的条目）。 */
function OperationsBlock({
  filter,
  onFilterChange,
}: {
  filter: string;
  onFilterChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const operations = useQuery({
    queryKey: [...settingsKeys.operations, filter],
    queryFn: () =>
      operationHistoryApi.listOperations(
        filter === ALL_OPTION ? {} : { status: filter },
      ),
  });

  return (
    <SettingsRow
      label={t("settings.operationHistory.operationsLabel")}
      description={t("settings.operationHistory.operationsHint")}
    >
      <div className="max-w-reading flex flex-col gap-3">
        <StatusFilterSelect
          filter={filter}
          onFilterChange={onFilterChange}
          options={OPERATION_STATUS_OPTIONS}
          optionLabel={(value) =>
            t(`settings.operationHistory.operationStatus.${value}`)
          }
        />

        {operations.isPending ? (
          <p role="status" className="text-label text-muted-foreground">
            <Spinner aria-hidden="true" />{" "}
            {t("settings.operationHistory.loading")}
          </p>
        ) : operations.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{operations.error.message}</AlertDescription>
          </Alert>
        ) : operations.data.length === 0 ? (
          <p className="text-label text-muted-foreground">
            {t("settings.operationHistory.operationsEmpty")}
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {operations.data.map((operation) => (
              <OperationRow key={operation.id} operation={operation} />
            ))}
          </ul>
        )}
      </div>
    </SettingsRow>
  );
}

/** 单条操作行：动作 / 目标 / 状态 / 结果 / 错误码 / 时间（工单验收字段）。 */
function OperationRow({ operation }: { operation: AgentOperationOut }) {
  const { t } = useTranslation();
  const target = describeTarget(operation);
  return (
    <li className="bg-surface-subtle flex items-center gap-2 rounded-md px-2.5 py-1.5">
      <span className="text-label font-label text-ink min-w-0 truncate">
        {t(`settings.operationHistory.action.${operation.action}`)}
      </span>
      {target ? (
        <span className="text-label text-muted-foreground min-w-0 flex-1 truncate">
          {target}
        </span>
      ) : (
        <span className="min-w-0 flex-1" />
      )}
      <span
        className={`text-label font-label min-w-16 ${statusTone(operation.status)}`}
      >
        {t(`settings.operationHistory.operationStatus.${operation.status}`)}
      </span>
      {operation.error_code ? (
        <span className="text-destructive text-label shrink-0">
          {operation.error_code}
        </span>
      ) : null}
      <span className="text-label text-muted-foreground shrink-0">
        {formatTime(operation.created_at)}
      </span>
    </li>
  );
}

/** 目标摘述：优先载荷里的对象名称（建课→课程名），否则结果里的对象 id 缩写。 */
function describeTarget(operation: AgentOperationOut): string {
  const name = operation.payload["name"];
  if (typeof name === "string" && name.trim()) {
    return name;
  }
  for (const key of ["course_id", "record_id"] as const) {
    const value = operation.result?.[key];
    if (typeof value === "string" && value) {
      return `#${value.slice(0, 8)}`;
    }
  }
  return "";
}

/** 模式切换审计（agent_activity）：本阶段无写入者，恒空态。 */
function ActivityBlock() {
  const { t } = useTranslation();
  const activity = useQuery({
    queryKey: settingsKeys.agentActivity,
    queryFn: () => operationHistoryApi.listActivity(),
  });

  return (
    <SettingsRow
      label={t("settings.operationHistory.activityLabel")}
      description={t("settings.operationHistory.activityHint")}
    >
      <div className="max-w-reading flex flex-col gap-2">
        {activity.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{activity.error.message}</AlertDescription>
          </Alert>
        ) : activity.data && activity.data.length > 0 ? (
          <ul className="flex flex-col gap-1.5">
            {activity.data.map((entry) => (
              <li
                key={entry.id}
                className="bg-surface-subtle flex items-center gap-2 rounded-md px-2.5 py-1.5"
              >
                <span className="text-label font-label text-ink">
                  {t("settings.operationHistory.activity.switch", {
                    from: t(
                      `settings.operationHistory.authMode.${entry.from_mode}`,
                    ),
                    to: t(
                      `settings.operationHistory.authMode.${entry.to_mode}`,
                    ),
                  })}
                </span>
                <span className="text-label text-muted-foreground min-w-0 flex-1 truncate">
                  {entry.scope === "SESSION" && entry.session_id
                    ? t("settings.operationHistory.activity.sessionScope")
                    : t("settings.operationHistory.activity.globalScope")}
                </span>
                <span className="text-label text-muted-foreground shrink-0">
                  {formatTime(entry.created_at)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-label text-muted-foreground">
            {t("settings.operationHistory.activityEmpty")}
          </p>
        )}
      </div>
    </SettingsRow>
  );
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString();
}
