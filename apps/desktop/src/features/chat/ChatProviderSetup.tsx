import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { KeyRound, Settings } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";

/**
 * “未配置 AI 服务”空态的就地配置卡：复用既有供应商配置 API，
 * 保存成功后查询失效，ChatSessionPage 随 provider 状态切回输入区。
 */
export function ChatProviderSetup({ hasApiKey }: { hasApiKey: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");

  const saveProvider = useMutation({
    mutationFn: () =>
      settingsApi.updateLlmProvider({
        base_url: baseUrl.trim(),
        model: model.trim(),
        api_key: apiKey,
        clear_api_key: false,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: settingsKeys.llmProvider,
      });
    },
  });

  const canSave =
    baseUrl.trim().length > 0 &&
    model.trim().length > 0 &&
    (apiKey.length > 0 || hasApiKey);

  return (
    <div className="border-border bg-surface-subtle/40 rounded-card border p-6">
      <div className="flex items-center gap-3">
        <Settings aria-hidden="true" className="text-muted-foreground size-5" />
        <h2 className="text-section font-section text-ink">
          {t("chat.provider.title")}
        </h2>
      </div>
      <p className="text-body text-muted-foreground mt-2">
        {t("chat.provider.description")}
      </p>
      <form
        className="mt-5 flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (canSave && !saveProvider.isPending) saveProvider.mutate();
        }}
      >
        <Field>
          <FieldLabel htmlFor="chat-provider-base-url">
            {t("chat.provider.baseUrl")}
          </FieldLabel>
          <Input
            id="chat-provider-base-url"
            value={baseUrl}
            placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
            disabled={saveProvider.isPending}
            onChange={(event) => setBaseUrl(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="chat-provider-model">
            {t("chat.provider.model")}
          </FieldLabel>
          <Input
            id="chat-provider-model"
            value={model}
            placeholder="qwen-plus"
            disabled={saveProvider.isPending}
            onChange={(event) => setModel(event.target.value)}
          />
          <FieldDescription>{t("chat.provider.modelHint")}</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="chat-provider-api-key">
            {t("chat.provider.apiKey")}
          </FieldLabel>
          <Input
            id="chat-provider-api-key"
            type="password"
            value={apiKey}
            placeholder={
              hasApiKey
                ? t("chat.provider.apiKeyKept")
                : t("chat.provider.apiKeyPlaceholder")
            }
            disabled={saveProvider.isPending}
            onChange={(event) => setApiKey(event.target.value)}
          />
        </Field>

        {saveProvider.isError ? (
          <Alert variant="destructive" className="w-auto">
            <AlertDescription>{saveProvider.error.message}</AlertDescription>
          </Alert>
        ) : null}
        {saveProvider.isSuccess ? (
          <p
            role="status"
            className="text-body text-muted-foreground flex items-center gap-2"
          >
            <KeyRound aria-hidden="true" className="size-4" />
            {t("chat.provider.savedFeedback")}
          </p>
        ) : null}

        <div>
          <Button type="submit" disabled={!canSave || saveProvider.isPending}>
            {saveProvider.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("chat.provider.saving")}
              />
            ) : null}
            {t("chat.provider.save")}
          </Button>
        </div>
      </form>
    </div>
  );
}
