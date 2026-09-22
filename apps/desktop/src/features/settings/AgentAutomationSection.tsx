import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Field, FieldLabel } from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  AUTH_MODES,
  agentAuthApi,
  agentKeys,
  isAuthMode,
} from "@/features/agent/api/authMode";
import {
  SettingsChoiceRow,
  SettingsPanelHeader,
} from "@/features/settings/SettingsLayout";

/** 设置页「Agent 自动化」分区（通用 Agent 第二阶段工单 02）：全局默认授权档
 * 三选一。默认＝请求批准（与确认卡流程一致）；「帮我批准」＝单对象创建等
 * 低风险操作免确认自动执行；「完全访问」＝除禁止项外全部自动执行。切换改
 * settings.json 偏离项并写模式切换审计（操作历史分区可见），只影响新会话
 * 与未携带会话覆盖的请求。 */
export function AgentAutomationSection() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const authMode = useQuery({
    queryKey: agentKeys.authMode,
    queryFn: () => agentAuthApi.getAuthMode(),
  });
  const switchMode = useMutation({
    mutationFn: ({
      to,
    }: {
      to: NonNullable<typeof authMode.data>["auth_mode"];
    }) => agentAuthApi.putAuthMode(to),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: agentKeys.authMode });
    },
  });

  return (
    <section
      aria-labelledby="settings-agent-automation-title"
      className="max-w-5xl"
    >
      <SettingsPanelHeader
        id="settings-agent-automation-title"
        title={t("settings.agentAutomation.title")}
      />
      <p className="text-body text-muted-foreground max-w-reading mt-2">
        {t("settings.agentAutomation.description")}
      </p>
      <div className="mt-8">
        {authMode.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{authMode.error.message}</AlertDescription>
          </Alert>
        ) : authMode.data ? (
          <SettingsChoiceRow label={t("settings.agentAutomation.modeLegend")}>
            <RadioGroup
              className="flex flex-wrap gap-x-5 gap-y-3"
              value={authMode.data.auth_mode}
              onValueChange={(value) => {
                if (isAuthMode(value)) {
                  switchMode.mutate({ to: value });
                }
              }}
              disabled={switchMode.isPending}
            >
              {AUTH_MODES.map((mode) => {
                const id = `agent-auth-mode-${mode}`;
                return (
                  <Field key={id} orientation="horizontal" className="w-auto">
                    <RadioGroupItem id={id} value={mode} />
                    <FieldLabel htmlFor={id}>
                      {t(`settings.operationHistory.authMode.${mode}`)}
                    </FieldLabel>
                  </Field>
                );
              })}
            </RadioGroup>
            <ul className="mt-3 flex flex-col gap-1">
              {AUTH_MODES.map((mode) => (
                <li key={mode} className="text-label text-muted-foreground">
                  {t(`settings.operationHistory.authMode.${mode}`)}
                  {" — "}
                  {t(`settings.agentAutomation.mode.${mode}`)}
                </li>
              ))}
            </ul>
            {switchMode.isError ? (
              <p role="alert" className="text-destructive text-label mt-2">
                {switchMode.error.message}
              </p>
            ) : null}
          </SettingsChoiceRow>
        ) : null}
      </div>
    </section>
  );
}
