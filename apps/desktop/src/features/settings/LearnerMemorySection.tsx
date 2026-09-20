import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { settingsKeys } from "@/features/settings/api/keys";
import {
  learnerMemoryApi,
  type LearnerPreferenceOut,
} from "@/features/settings/api/learnerMemory";
import {
  SettingsPanelHeader,
  SettingsRow,
} from "@/features/settings/SettingsLayout";

/** 显式偏好条数上限（与后端 LearnerPreferenceUpdate 同源约束）。 */
const MAX_ITEMS = 20;

/** 学习画像「AI 记忆」区（工单 06，ADR-0025）：显式偏好直编（即改即存）、
 * 观察偏好治理（置信度/证据数/确认时间 + 删除）、长期记忆外发独立开关。
 * 记忆写入仅两类入口：此处直接编辑、对话中「记住…」提案经确认卡写入。 */
export function LearnerMemorySection() {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: settingsKeys.learnerMemory,
    queryFn: () => learnerMemoryApi.get(),
  });

  if (query.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground mt-10 flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("settings.learnerMemory.loading")}
      </p>
    );
  }
  if (query.isError) {
    return (
      <div className="mt-10">
        <Alert variant="destructive">
          <AlertDescription>{query.error.message}</AlertDescription>
        </Alert>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => void query.refetch()}
        >
          {t("settings.learnerMemory.retry")}
        </Button>
      </div>
    );
  }
  return (
    <section
      aria-labelledby="settings-learner-memory-title"
      className="max-w-5xl"
    >
      <SettingsPanelHeader
        id="settings-learner-memory-title"
        title={t("settings.learnerMemory.title")}
      />
      <p className="text-body text-muted-foreground max-w-reading mt-2">
        {t("settings.learnerMemory.description")}
      </p>
      <div className="mt-8 flex flex-col gap-8">
        <ExplicitItems data={query.data} />
        <ObservedEntries data={query.data} />
        <OutboundToggle data={query.data} />
      </div>
    </section>
  );
}

/** 显式偏好：条目即改即存（添加/删除直接 PUT 全量列表），去重由后端兜底。 */
function ExplicitItems({ data }: { data: LearnerPreferenceOut }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const save = useMutation({
    mutationFn: (items: string[]) => learnerMemoryApi.save({ items }),
    // 失效重取即回显服务端事实（去重/清洗后的列表）。
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: settingsKeys.learnerMemory }),
  });

  const addItem = () => {
    const item = draft.trim();
    if (!item || save.isPending) return;
    setDraft("");
    save.mutate([...data.explicit_items, item].slice(0, MAX_ITEMS));
  };
  const removeItem = (index: number) => {
    if (save.isPending) return;
    save.mutate(data.explicit_items.filter((_, current) => current !== index));
  };

  return (
    <SettingsRow
      label={t("settings.learnerMemory.explicitLabel")}
      description={t("settings.learnerMemory.explicitHint")}
    >
      <div className="max-w-reading flex flex-col gap-2">
        {data.explicit_items.length === 0 ? (
          <p className="text-label text-muted-foreground">
            {t("settings.learnerMemory.explicitEmpty")}
          </p>
        ) : (
          <ul
            className="flex flex-col gap-1.5"
            aria-label={t("settings.learnerMemory.explicitLabel")}
          >
            {data.explicit_items.map((item, index) => (
              <li
                key={`${item}-${index}`}
                className="bg-surface-subtle flex items-center gap-2 rounded-md px-2.5 py-1.5"
              >
                <span className="text-label text-ink min-w-0 flex-1 break-words">
                  {item}
                </span>
                <button
                  type="button"
                  className="hover:bg-surface-raised rounded p-1"
                  aria-label={t("settings.learnerMemory.explicitRemove", {
                    item,
                  })}
                  disabled={save.isPending}
                  onClick={() => removeItem(index)}
                >
                  <X className="size-3.5" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex items-center gap-2">
          <Input
            value={draft}
            maxLength={100}
            placeholder={t("settings.learnerMemory.explicitPlaceholder")}
            disabled={save.isPending || data.explicit_items.length >= MAX_ITEMS}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addItem();
              }
            }}
          />
          <Button
            variant="outline"
            size="sm"
            disabled={
              save.isPending ||
              !draft.trim() ||
              data.explicit_items.length >= MAX_ITEMS
            }
            onClick={addItem}
          >
            {save.isPending ? (
              <Spinner data-icon="inline-start" aria-hidden="true" />
            ) : (
              <Plus className="size-3.5" aria-hidden />
            )}
            {t("settings.learnerMemory.explicitAdd")}
          </Button>
        </div>
        {save.isError ? (
          <p role="alert" className="text-destructive text-label">
            {save.error.message}
          </p>
        ) : null}
      </div>
    </SettingsRow>
  );
}

/** 观察偏好：展示置信度/证据数/确认时间，删除即失（永不覆盖显式偏好）。 */
function ObservedEntries({ data }: { data: LearnerPreferenceOut }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: (key: string) => learnerMemoryApi.deleteObserved(key),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: settingsKeys.learnerMemory }),
  });
  const entries = Object.entries(data.observed_entries);

  return (
    <SettingsRow
      label={t("settings.learnerMemory.observedLabel")}
      description={t("settings.learnerMemory.observedHint")}
    >
      <div className="max-w-reading flex flex-col gap-2">
        {entries.length === 0 ? (
          <p className="text-label text-muted-foreground">
            {t("settings.learnerMemory.observedEmpty")}
          </p>
        ) : (
          <ul
            className="flex flex-col gap-1.5"
            aria-label={t("settings.learnerMemory.observedLabel")}
          >
            {entries.map(([key, value]) => (
              <li
                key={key}
                className="bg-surface-subtle flex items-center gap-2 rounded-md px-2.5 py-1.5"
              >
                <span className="text-label text-ink min-w-0 flex-1 break-words">
                  {t("settings.learnerMemory.observedEntry", { key, value })}
                </span>
                <button
                  type="button"
                  className="hover:bg-surface-raised rounded p-1"
                  aria-label={t("settings.learnerMemory.observedRemove", {
                    key,
                  })}
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(key)}
                >
                  <X className="size-3.5" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        {/* 置信度/证据数/确认时间是单例表级字段（0026 DDL），列表下方统一展示一次。 */}
        {entries.length > 0 ? (
          <p className="text-label text-muted-foreground">
            {t("settings.learnerMemory.observedMeta", {
              confidence: Math.round((data.observed_confidence ?? 0) * 100),
              evidence: data.evidence_count,
              time: data.last_observed_at
                ? new Date(data.last_observed_at).toLocaleDateString()
                : t("settings.learnerMemory.observedTimeUnknown"),
            })}
          </p>
        ) : null}
        {remove.isError ? (
          <p role="alert" className="text-destructive text-label">
            {remove.error.message}
          </p>
        ) : null}
      </div>
    </SettingsRow>
  );
}

/** 长期记忆外发开关：关闭=记忆保留本地、不再注入发给 AI 的内容；本地管理不受影响。
 * 控件形态对齐设置页先例（自启动行）：左列 label 经 htmlFor 关联，右列开关 + 状态文字。 */
function OutboundToggle({ data }: { data: LearnerPreferenceOut }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => learnerMemoryApi.setOutbound(enabled),
    // 失效重取即回显服务端事实（含三态描述文案所需的外发状态）。
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: settingsKeys.learnerMemory }),
  });
  const outbound = data.memory_outbound;

  return (
    <SettingsRow
      label={t("settings.learnerMemory.outboundLabel")}
      htmlFor="learner-memory-outbound"
      description={
        outbound.enabled
          ? outbound.consent_current
            ? t("settings.learnerMemory.outboundHintOn")
            : t("settings.learnerMemory.outboundConsentStale")
          : t("settings.learnerMemory.outboundHintOff")
      }
    >
      <div className="flex items-center gap-3">
        <Switch
          id="learner-memory-outbound"
          checked={outbound.enabled}
          disabled={toggle.isPending}
          onCheckedChange={(checked) => toggle.mutate(Boolean(checked))}
        />
        <p className="text-label font-label text-ink">
          {outbound.enabled
            ? t("settings.learnerMemory.outboundStateOn")
            : t("settings.learnerMemory.outboundStateOff")}
        </p>
      </div>
      {toggle.isError ? (
        <p role="alert" className="text-destructive text-label">
          {toggle.error.message}
        </p>
      ) : null}
    </SettingsRow>
  );
}
