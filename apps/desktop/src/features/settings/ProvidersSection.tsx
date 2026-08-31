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

// DashScope OpenAI 兼容模式端点与默认模型：一键填充后仍可修改（plan 14 定稿预设）。
const DASHSCOPE_PRESET_BASE_URL =
  "https://dashscope.aliyuncs.com/compatible-mode/v1";
const DASHSCOPE_PRESET_MODEL = "qwen-plus";

type LlmProviderOut = components["schemas"]["LlmProviderOut"];
type TencentAsrProviderOut = components["schemas"]["TencentAsrProviderOut"];

export function ProvidersSection() {
  const { t } = useTranslation();
  return (
    <div className="border-border max-w-reading mt-8 border-t pt-8">
      <h2 className="text-section font-section text-ink">
        {t("settings.providers.sectionTitle")}
      </h2>
      <p className="max-w-reading text-body text-muted-foreground">
        {t("settings.providers.sectionDescription")}
      </p>
      <div className="mt-6 flex flex-col gap-8">
        <LlmProviderCard />
        <TencentAsrCard />
      </div>
    </div>
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
  return (
    <section aria-labelledby="providers-llm-title">
      <h3
        id="providers-llm-title"
        className="text-section font-section text-ink"
      >
        {t("settings.providers.llm.title")}
      </h3>
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
    mutationFn: () =>
      settingsApi.updateLlmProvider({
        base_url: baseUrl.trim(),
        model: model.trim(),
        api_key: apiKey,
        clear_api_key: clearApiKey,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: settingsKeys.llmProvider,
      });
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
      className="mt-4 flex flex-col gap-5"
      onChange={() => {
        save.reset();
        test.reset();
      }}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSave && !save.isPending) save.mutate();
      }}
    >
      <Field>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <FieldLabel htmlFor="provider-llm-base-url">
            {t("settings.providers.llm.baseUrl")}
          </FieldLabel>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={save.isPending}
            onClick={() => {
              setBaseUrl(DASHSCOPE_PRESET_BASE_URL);
              setModel(DASHSCOPE_PRESET_MODEL);
            }}
          >
            {t("settings.providers.llm.dashscopePreset")}
          </Button>
        </div>
        <Input
          id="provider-llm-base-url"
          value={baseUrl}
          placeholder={DASHSCOPE_PRESET_BASE_URL}
          disabled={save.isPending}
          onChange={(event) => setBaseUrl(event.target.value)}
        />
      </Field>
      <Field>
        <FieldLabel htmlFor="provider-llm-model">
          {t("settings.providers.llm.model")}
        </FieldLabel>
        <Input
          id="provider-llm-model"
          value={model}
          placeholder={DASHSCOPE_PRESET_MODEL}
          disabled={save.isPending}
          onChange={(event) => setModel(event.target.value)}
        />
        <FieldDescription>
          {t("settings.providers.llm.modelHint")}
        </FieldDescription>
      </Field>
      <Field>
        <FieldLabel htmlFor="provider-llm-api-key">
          {t("settings.providers.llm.apiKey")}
        </FieldLabel>
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
      </Field>
      {hasApiKey ? (
        <Field orientation="horizontal">
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

      {save.isError ? (
        <Alert variant="destructive" className="w-auto">
          <AlertDescription>{save.error.message}</AlertDescription>
        </Alert>
      ) : null}
      {save.isSuccess ? (
        <p role="status" className="text-body text-muted-foreground">
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
        <p role="status" className="text-body text-muted-foreground">
          {t("settings.providers.llm.testSucceeded", {
            model: test.data.model,
          })}
        </p>
      ) : null}
      {test.isError ? (
        <Alert variant="destructive" className="w-auto">
          <AlertDescription>{test.error.message}</AlertDescription>
        </Alert>
      ) : null}
      <FieldDescription>
        {t("settings.providers.llm.embeddingNote")}
      </FieldDescription>
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
  return (
    <section aria-labelledby="providers-asr-title">
      <h3
        id="providers-asr-title"
        className="text-section font-section text-ink"
      >
        {t("settings.providers.asr.title")}
      </h3>
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
      className="mt-4 flex flex-col gap-5"
      onChange={() => {
        save.reset();
        test.reset();
      }}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSave && !save.isPending) save.mutate();
      }}
    >
      <Field>
        <FieldLabel htmlFor="provider-asr-secret-id">SecretId</FieldLabel>
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
      </Field>
      <Field>
        <FieldLabel htmlFor="provider-asr-secret-key">SecretKey</FieldLabel>
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
      </Field>
      <Field>
        <FieldLabel htmlFor="provider-asr-region">
          {t("settings.providers.asr.region")}
        </FieldLabel>
        <Input
          id="provider-asr-region"
          value={region}
          placeholder={t("settings.providers.asr.regionPlaceholder")}
          disabled={save.isPending}
          onChange={(event) => setRegion(event.target.value)}
        />
      </Field>
      {hasCredentials ? (
        <Field orientation="horizontal">
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

      {save.isError ? (
        <Alert variant="destructive" className="w-auto">
          <AlertDescription>{save.error.message}</AlertDescription>
        </Alert>
      ) : null}
      {save.isSuccess ? (
        <p role="status" className="text-body text-muted-foreground">
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
        <p role="status" className="text-body text-muted-foreground">
          {t("settings.providers.asr.testSucceeded", {
            region: test.data.region,
          })}
        </p>
      ) : null}
      {test.isError ? (
        <Alert variant="destructive" className="w-auto">
          <AlertDescription>{test.error.message}</AlertDescription>
        </Alert>
      ) : null}
      <FieldDescription>
        {t("settings.providers.asr.consentNote")}
      </FieldDescription>
    </form>
  );
}
