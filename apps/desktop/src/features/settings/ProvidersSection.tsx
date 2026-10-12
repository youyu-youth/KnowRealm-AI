import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import type { components } from "@knowrealm/api-types";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";
import { LlmUsageCard } from "@/features/settings/LlmUsageCard";
import { ModelBudgetFields } from "@/features/settings/ModelBudgetFields";
import {
  SettingsActions,
  SettingsPanelHeader,
  SettingsRow,
} from "@/features/settings/SettingsLayout";

// DashScope OpenAI 兼容模式端点与默认模型：一键填充后仍可修改（plan 14 定稿预设）。
const DASHSCOPE_PRESET_BASE_URL =
  "https://dashscope.aliyuncs.com/compatible-mode/v1";
const DASHSCOPE_PRESET_MODEL = "qwen-plus";

type LlmProviderOut = components["schemas"]["LlmProviderOut"];
type TencentAsrProviderOut = components["schemas"]["TencentAsrProviderOut"];
type WebSearchProviderOut = components["schemas"]["WebSearchProviderOut"];

export function ProvidersSection() {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="settings-providers-title" className="max-w-5xl">
      <SettingsPanelHeader
        id="settings-providers-title"
        title={t("settings.navigation.ai")}
      />
      <div className="mt-8 flex flex-col gap-12">
        <LlmProviderCard />
        <TencentAsrCard />
        <WebSearchCard />
        <LlmUsageCard />
      </div>
    </section>
  );
}

// 健康检查徽章（#38）：key 配置状态即时展示；连通性探测由卡上「测试连接」按需触发，不做启动/打开期自动探测。
function StatusBadge({
  ok,
  okLabel,
  missingLabel,
}: {
  ok: boolean;
  okLabel: string;
  missingLabel: string;
}) {
  return (
    <span
      className={`${ok ? "bg-success-soft text-success-foreground" : "bg-danger/10 text-danger"} text-label rounded-xs px-2 py-1`}
    >
      {ok ? okLabel : missingLabel}
    </span>
  );
}

function SectionError({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  return (
    <section>
      <h3 className="text-section font-section text-ink">{title}</h3>
      <p className="text-body text-muted-foreground mt-2">{message}</p>
      <Button variant="outline" className="mt-4" onClick={onRetry}>
        {t("settings.providers.retry")}
      </Button>
    </section>
  );
}

// 导出供首启向导（06）复用：卡片自带查询与保存，设置页与向导共用同一份配置体验。
export function LlmProviderCard() {
  const { t } = useTranslation();
  const provider = useQuery({
    queryKey: settingsKeys.llmProvider,
    queryFn: settingsApi.getLlmProvider,
  });

  if (provider.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("settings.providers.loading")}
      </p>
    );
  }
  if (provider.isError) {
    return (
      <SectionError
        title={t("settings.providers.llm.title")}
        message={provider.error.message}
        onRetry={() => void provider.refetch()}
      />
    );
  }

  const data = provider.data.provider;
  const hasApiKey = data?.has_api_key ?? false;
  return (
    <section aria-labelledby="providers-llm-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3
          id="providers-llm-title"
          className="text-section font-section text-ink"
        >
          {t("settings.providers.llm.title")}
        </h3>
        <StatusBadge
          ok={hasApiKey}
          okLabel={t("settings.providers.llm.configured")}
          missingLabel={t("settings.providers.llm.missingKey")}
        />
      </div>
      {hasApiKey ? null : (
        <p className="text-body text-danger mt-1">
          {t("settings.providers.llm.missingKeyHint")}
        </p>
      )}
      <p className="text-body text-muted-foreground mt-1">
        {t("settings.providers.llm.description")}
      </p>
      {/* key 随服务端配置事实变化：保存成功并重取后表单以最新配置重挂载（密钥输入随之清空）。 */}
      <LlmProviderForm
        key={`${data?.base_url ?? ""}|${data?.model ?? ""}|${data?.has_api_key ?? false}|${data?.api_key_hint ?? ""}`}
        initial={data}
      />
    </section>
  );
}

function LlmProviderForm({ initial }: { initial: LlmProviderOut | null }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "");
  const [model, setModel] = useState(initial?.model ?? "");
  const [apiKey, setApiKey] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const hasApiKey = initial?.has_api_key ?? false;

  const save = useMutation({
    mutationFn: (modelBudget: components["schemas"]["ModelBudgetConfig"]) =>
      settingsApi.updateLlmProvider({
        base_url: baseUrl.trim(),
        model: model.trim(),
        api_key: apiKey,
        clear_api_key: clearApiKey,
        model_budget: modelBudget,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: settingsKeys.llmProvider,
      });
      await queryClient.invalidateQueries({ queryKey: ["chat", "context"] });
    },
  });
  const test = useMutation({ mutationFn: settingsApi.testLlmProvider });

  const savedHasKey = save.data?.provider?.has_api_key ?? hasApiKey;
  const canSave =
    baseUrl.trim().length > 0 &&
    model.trim().length > 0 &&
    (clearApiKey || apiKey.length > 0 || hasApiKey);

  return (
    <form
      className="mt-6 flex flex-col gap-7"
      onChange={() => {
        save.reset();
        test.reset();
      }}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSave && !save.isPending) {
          const fields = new FormData(event.currentTarget);
          const numeric = (key: string) =>
            fields.get(key) ? Number(fields.get(key)) : null;
          save.mutate({
            input_limit: numeric("input_limit"),
            context_window: numeric("context_window"),
            max_output: numeric("max_output"),
            answer_output: numeric("answer_output") ?? 4096,
            summary_output: numeric("summary_output") ?? 1024,
          });
        }
      }}
    >
      <SettingsRow
        label={t("settings.providers.llm.baseUrl")}
        htmlFor="provider-llm-base-url"
      >
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
          <Input
            id="provider-llm-base-url"
            value={baseUrl}
            placeholder={DASHSCOPE_PRESET_BASE_URL}
            disabled={save.isPending}
            onChange={(event) => setBaseUrl(event.target.value)}
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="shrink-0"
            disabled={save.isPending}
            onClick={() => {
              setBaseUrl(DASHSCOPE_PRESET_BASE_URL);
              setModel(DASHSCOPE_PRESET_MODEL);
            }}
          >
            {t("settings.providers.llm.dashscopePreset")}
          </Button>
        </div>
      </SettingsRow>
      <SettingsRow
        label={t("settings.providers.llm.model")}
        description={t("settings.providers.llm.modelHint")}
        htmlFor="provider-llm-model"
      >
        <Input
          id="provider-llm-model"
          value={model}
          placeholder={DASHSCOPE_PRESET_MODEL}
          disabled={save.isPending}
          onChange={(event) => setModel(event.target.value)}
        />
      </SettingsRow>
      <SettingsRow
        label={t("settings.providers.llm.apiKey")}
        htmlFor="provider-llm-api-key"
      >
        <Input
          id="provider-llm-api-key"
          type="password"
          value={apiKey}
          placeholder={
            hasApiKey
              ? (initial?.api_key_hint ??
                t("settings.providers.llm.apiKeyKept"))
              : t("settings.providers.llm.apiKeyPlaceholder")
          }
          disabled={save.isPending || clearApiKey}
          onChange={(event) => setApiKey(event.target.value)}
        />
        {hasApiKey ? (
          <Field orientation="horizontal" className="mt-3">
            <Checkbox
              id="provider-llm-clear-api-key"
              checked={clearApiKey}
              onCheckedChange={(checked) => {
                setClearApiKey(checked === true);
                save.reset();
                test.reset();
              }}
              disabled={save.isPending}
            />
            <FieldLabel htmlFor="provider-llm-clear-api-key">
              {t("settings.providers.llm.clearApiKey")}
            </FieldLabel>
          </Field>
        ) : null}
      </SettingsRow>

      <ModelBudgetFields
        key={`${baseUrl.trim()}|${model.trim()}`}
        initial={
          baseUrl.trim() === initial?.base_url &&
          model.trim() === initial?.model
            ? initial
            : null
        }
        disabled={save.isPending}
      />
      <SettingsActions>
        {save.isError ? (
          <Alert variant="destructive" className="mb-3 w-auto">
            <AlertDescription>{save.error.message}</AlertDescription>
          </Alert>
        ) : null}
        {save.isSuccess ? (
          <p role="status" className="text-body text-muted-foreground mb-3">
            {t("settings.providers.llm.savedFeedback")}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" disabled={!canSave || save.isPending}>
            {save.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("settings.providers.llm.saving")}
              />
            ) : null}
            {t("settings.providers.llm.save")}
          </Button>
          {savedHasKey ? (
            <Button
              type="button"
              variant="outline"
              disabled={test.isPending}
              onClick={() => test.mutate()}
            >
              {test.isPending ? (
                <Spinner
                  data-icon="inline-start"
                  aria-label={t("settings.providers.llm.testing")}
                />
              ) : null}
              {t("settings.providers.llm.test")}
            </Button>
          ) : null}
        </div>
        {test.isSuccess ? (
          <p role="status" className="text-body text-muted-foreground mt-3">
            {t("settings.providers.llm.testSucceeded", {
              model: test.data.model,
            })}
          </p>
        ) : null}
        {test.isError ? (
          <Alert variant="destructive" className="mt-3 w-auto">
            <AlertDescription>{test.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <FieldDescription className="mt-3">
          {t("settings.providers.llm.embeddingNote")}
        </FieldDescription>
      </SettingsActions>
    </form>
  );
}

export function TencentAsrCard() {
  const { t } = useTranslation();
  const provider = useQuery({
    queryKey: settingsKeys.tencentAsrProvider,
    queryFn: settingsApi.getTencentAsrProvider,
  });

  if (provider.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("settings.providers.loading")}
      </p>
    );
  }
  if (provider.isError) {
    return (
      <SectionError
        title={t("settings.providers.asr.title")}
        message={provider.error.message}
        onRetry={() => void provider.refetch()}
      />
    );
  }

  const data = provider.data.provider;
  const hasCredentials = data?.has_credentials ?? false;
  return (
    <section aria-labelledby="providers-asr-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3
          id="providers-asr-title"
          className="text-section font-section text-ink"
        >
          {t("settings.providers.asr.title")}
        </h3>
        <StatusBadge
          ok={hasCredentials}
          okLabel={t("settings.providers.asr.configured")}
          missingLabel={t("settings.providers.asr.missingCredentials")}
        />
      </div>
      {hasCredentials ? null : (
        <p className="text-body text-danger mt-1">
          {t("settings.providers.asr.missingCredentialsHint")}
        </p>
      )}
      <p className="text-body text-muted-foreground mt-1">
        {t("settings.providers.asr.description")}
      </p>
      <TencentAsrForm
        key={`${data?.region ?? ""}|${data?.has_credentials ?? false}|${data?.secret_id_hint ?? ""}`}
        initial={data}
      />
    </section>
  );
}

function TencentAsrForm({
  initial,
}: {
  initial: TencentAsrProviderOut | null;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [secretId, setSecretId] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [region, setRegion] = useState(initial?.region ?? "");
  const [clearSecretKey, setClearSecretKey] = useState(false);
  const hasCredentials = initial?.has_credentials ?? false;

  const save = useMutation({
    mutationFn: () =>
      settingsApi.updateTencentAsrProvider({
        region: region.trim(),
        secret_id: secretId,
        secret_key: secretKey,
        clear_secret_key: clearSecretKey,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: settingsKeys.tencentAsrProvider,
      });
    },
  });
  const test = useMutation({ mutationFn: settingsApi.testTencentAsrProvider });

  const savedHasCredentials =
    save.data?.provider?.has_credentials ?? hasCredentials;
  const canSave =
    region.trim().length > 0 &&
    (clearSecretKey ||
      (secretId.length > 0 && secretKey.length > 0) ||
      hasCredentials);

  return (
    <form
      className="mt-6 flex flex-col gap-7"
      onChange={() => {
        save.reset();
        test.reset();
      }}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSave && !save.isPending) save.mutate();
      }}
    >
      <SettingsRow label="SecretId" htmlFor="provider-asr-secret-id">
        <Input
          id="provider-asr-secret-id"
          type="password"
          value={secretId}
          placeholder={
            initial?.secret_id_hint ??
            t("settings.providers.asr.secretIdPlaceholder")
          }
          disabled={save.isPending || clearSecretKey}
          onChange={(event) => setSecretId(event.target.value)}
        />
      </SettingsRow>
      <SettingsRow label="SecretKey" htmlFor="provider-asr-secret-key">
        <Input
          id="provider-asr-secret-key"
          type="password"
          value={secretKey}
          placeholder={
            hasCredentials
              ? t("settings.providers.asr.kept")
              : t("settings.providers.asr.secretKeyPlaceholder")
          }
          disabled={save.isPending || clearSecretKey}
          onChange={(event) => setSecretKey(event.target.value)}
        />
      </SettingsRow>
      <SettingsRow
        label={t("settings.providers.asr.region")}
        htmlFor="provider-asr-region"
      >
        <Input
          id="provider-asr-region"
          value={region}
          placeholder={t("settings.providers.asr.regionPlaceholder")}
          disabled={save.isPending}
          onChange={(event) => setRegion(event.target.value)}
        />
        {hasCredentials ? (
          <Field orientation="horizontal" className="mt-3">
            <Checkbox
              id="provider-asr-clear"
              checked={clearSecretKey}
              onCheckedChange={(checked) => {
                setClearSecretKey(checked === true);
                save.reset();
                test.reset();
              }}
              disabled={save.isPending}
            />
            <FieldLabel htmlFor="provider-asr-clear">
              {t("settings.providers.asr.clear")}
            </FieldLabel>
          </Field>
        ) : null}
      </SettingsRow>

      <SettingsActions>
        {save.isError ? (
          <Alert variant="destructive" className="mb-3 w-auto">
            <AlertDescription>{save.error.message}</AlertDescription>
          </Alert>
        ) : null}
        {save.isSuccess ? (
          <p role="status" className="text-body text-muted-foreground mb-3">
            {t("settings.providers.asr.savedFeedback")}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" disabled={!canSave || save.isPending}>
            {save.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("settings.providers.asr.saving")}
              />
            ) : null}
            {t("settings.providers.asr.save")}
          </Button>
          {savedHasCredentials ? (
            <Button
              type="button"
              variant="outline"
              disabled={test.isPending}
              onClick={() => test.mutate()}
            >
              {test.isPending ? (
                <Spinner
                  data-icon="inline-start"
                  aria-label={t("settings.providers.asr.testing")}
                />
              ) : null}
              {t("settings.providers.asr.test")}
            </Button>
          ) : null}
        </div>
        {test.isSuccess ? (
          <p role="status" className="text-body text-muted-foreground mt-3">
            {t("settings.providers.asr.testSucceeded", {
              region: test.data.region,
            })}
          </p>
        ) : null}
        {test.isError ? (
          <Alert variant="destructive" className="mt-3 w-auto">
            <AlertDescription>{test.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <FieldDescription className="mt-3">
          {t("settings.providers.asr.consentNote")}
        </FieldDescription>
      </SettingsActions>
    </form>
  );
}

// 联网搜索供应商卡（B1）：模式对齐 LLM/ASR 卡；无同意门——配 key 即显式 opt-in，
// 外发知情说明写进卡片描述与测试注释。
export function WebSearchCard() {
  const { t } = useTranslation();
  const provider = useQuery({
    queryKey: settingsKeys.webSearchProvider,
    queryFn: settingsApi.getWebSearchProvider,
  });

  if (provider.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("settings.providers.loading")}
      </p>
    );
  }
  if (provider.isError) {
    return (
      <SectionError
        title={t("settings.providers.webSearch.title")}
        message={provider.error.message}
        onRetry={() => void provider.refetch()}
      />
    );
  }

  const data = provider.data.provider;
  const hasApiKey = data?.has_api_key ?? false;
  return (
    <section aria-labelledby="providers-web-search-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3
          id="providers-web-search-title"
          className="text-section font-section text-ink"
        >
          {t("settings.providers.webSearch.title")}
        </h3>
        <StatusBadge
          ok={hasApiKey}
          okLabel={t("settings.providers.webSearch.configured")}
          missingLabel={t("settings.providers.webSearch.missingKey")}
        />
      </div>
      {hasApiKey ? null : (
        <p className="text-body text-danger mt-1">
          {t("settings.providers.webSearch.missingKeyHint")}
        </p>
      )}
      <p className="text-body text-muted-foreground mt-1">
        {t("settings.providers.webSearch.description")}
      </p>
      <WebSearchForm
        key={`${data?.has_api_key ?? false}|${data?.api_key_hint ?? ""}`}
        initial={data ?? null}
      />
    </section>
  );
}

function WebSearchForm({ initial }: { initial: WebSearchProviderOut | null }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const hasApiKey = initial?.has_api_key ?? false;

  const save = useMutation({
    mutationFn: () =>
      settingsApi.updateWebSearchProvider({
        provider: "tavily",
        api_key: apiKey,
        clear_api_key: clearApiKey,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: settingsKeys.webSearchProvider,
      });
    },
  });
  const test = useMutation({ mutationFn: settingsApi.testWebSearchProvider });

  const savedHasKey = save.data?.provider?.has_api_key ?? hasApiKey;
  const canSave = clearApiKey || apiKey.length > 0 || hasApiKey;

  return (
    <form
      className="mt-6 flex flex-col gap-7"
      onChange={() => {
        save.reset();
        test.reset();
      }}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSave && !save.isPending) save.mutate();
      }}
    >
      <SettingsRow
        label={t("settings.providers.webSearch.apiKey")}
        htmlFor="provider-web-search-api-key"
      >
        <Input
          id="provider-web-search-api-key"
          type="password"
          value={apiKey}
          placeholder={
            hasApiKey
              ? (initial?.api_key_hint ??
                t("settings.providers.webSearch.apiKeyKept"))
              : t("settings.providers.webSearch.apiKeyPlaceholder")
          }
          disabled={save.isPending || clearApiKey}
          onChange={(event) => setApiKey(event.target.value)}
        />
        {hasApiKey ? (
          <Field orientation="horizontal" className="mt-3">
            <Checkbox
              id="provider-web-search-clear"
              checked={clearApiKey}
              onCheckedChange={(checked) => {
                setClearApiKey(checked === true);
                save.reset();
                test.reset();
              }}
              disabled={save.isPending}
            />
            <FieldLabel htmlFor="provider-web-search-clear">
              {t("settings.providers.webSearch.clearApiKey")}
            </FieldLabel>
          </Field>
        ) : null}
      </SettingsRow>

      <SettingsActions>
        {save.isError ? (
          <Alert variant="destructive" className="mb-3 w-auto">
            <AlertDescription>{save.error.message}</AlertDescription>
          </Alert>
        ) : null}
        {save.isSuccess ? (
          <p role="status" className="text-body text-muted-foreground mb-3">
            {t("settings.providers.webSearch.savedFeedback")}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" disabled={!canSave || save.isPending}>
            {save.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("settings.providers.webSearch.saving")}
              />
            ) : null}
            {t("settings.providers.webSearch.save")}
          </Button>
          {savedHasKey ? (
            <Button
              type="button"
              variant="outline"
              disabled={test.isPending}
              onClick={() => test.mutate()}
            >
              {test.isPending ? (
                <Spinner
                  data-icon="inline-start"
                  aria-label={t("settings.providers.webSearch.testing")}
                />
              ) : null}
              {t("settings.providers.webSearch.test")}
            </Button>
          ) : null}
        </div>
        {test.isSuccess ? (
          <p role="status" className="text-body text-muted-foreground mt-3">
            {t("settings.providers.webSearch.testSucceeded", {
              provider: test.data.provider,
            })}
          </p>
        ) : null}
        {test.isError ? (
          <Alert variant="destructive" className="mt-3 w-auto">
            <AlertDescription>{test.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <FieldDescription className="mt-3">
          {t("settings.providers.webSearch.testNote")}
        </FieldDescription>
      </SettingsActions>
    </form>
  );
}
