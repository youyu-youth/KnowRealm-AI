import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ShieldCheck } from "lucide-react";
import {
  AUTH_MODES,
  agentAuthApi,
  agentKeys,
  isAuthMode,
  type AuthMode,
} from "@/features/agent/api/authMode";
import { useChatUiStore } from "@/features/chat/chatUiStore";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const AUTH_MODE_LABEL_KEY = (mode: AuthMode) =>
  `settings.operationHistory.authMode.${mode}` as const;

type ChatAuthModeSectionProps = {
  sessionId: string;
};

/** 聊天右栏授权模式开关（通用 Agent 第二阶段工单 02）：会话内临时切换
 * 授权档位（按会话内存，重启回落全局默认——安全方向）；切换动作先写
 * 模式切换审计（from=当前生效档），成功后生效本地覆盖；发送消息时携带
 * 覆盖，未拨过＝全局默认档。 */
export function ChatAuthModeSection({ sessionId }: ChatAuthModeSectionProps) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  // 全局默认档（后端 settings.json 偏离项，缺省 REQUEST_APPROVAL）。
  const globalMode = useQuery({
    queryKey: agentKeys.authMode,
    queryFn: () => agentAuthApi.getAuthMode(),
    retry: false,
  });
  const sessionOverride = useChatUiStore(
    (state) => state.authModeBySession[sessionId],
  );
  const setSessionAuthMode = useChatUiStore(
    (state) => state.setSessionAuthMode,
  );
  const effectiveMode: AuthMode | undefined =
    sessionOverride ?? globalMode.data?.auth_mode;

  const switchMode = useMutation({
    mutationFn: ({ from, to }: { from: AuthMode; to: AuthMode }) =>
      agentAuthApi.postSessionSwitch(sessionId, from, to),
    onSuccess: (_result, variables) => {
      setError(null);
      // 审计落定后本地覆盖才生效：切换全程留痕（spec 决策 22）。
      setSessionAuthMode(sessionId, variables.to);
    },
    onError: (exc: unknown) => {
      setError(exc instanceof Error ? exc.message : String(exc));
    },
  });

  return (
    <section className="px-5 pt-6">
      <h2 className="text-section font-section text-ink-strong flex items-center gap-1.5">
        <ShieldCheck className="text-ink-muted size-4" aria-hidden="true" />
        {t("chat.authMode.title")}
      </h2>
      <p className="text-label text-muted-foreground mt-1">
        {t("chat.authMode.hint")}
      </p>
      <div className="mt-3">
        <Select
          items={AUTH_MODES.map((mode) => ({
            value: mode,
            label: t(AUTH_MODE_LABEL_KEY(mode)),
          }))}
          value={effectiveMode ?? null}
          onValueChange={(value) => {
            if (
              isAuthMode(value) &&
              effectiveMode !== undefined &&
              value !== effectiveMode
            ) {
              switchMode.mutate({ from: effectiveMode, to: value });
            }
          }}
          disabled={
            switchMode.isPending ||
            globalMode.isPending ||
            effectiveMode === undefined
          }
        >
          <SelectTrigger
            id="chat-auth-mode"
            className="w-full"
            aria-label={t("chat.authMode.title")}
          >
            <SelectValue placeholder={t("chat.authMode.placeholder")}>
              {effectiveMode ? t(AUTH_MODE_LABEL_KEY(effectiveMode)) : null}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {AUTH_MODES.map((mode) => (
                <SelectItem key={mode} value={mode}>
                  {t(AUTH_MODE_LABEL_KEY(mode))}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <p className="text-label text-muted-foreground mt-1.5">
          {effectiveMode ? t(`chat.authMode.mode.${effectiveMode}`) : null}
        </p>
        {error ? (
          <p role="alert" className="text-destructive text-label mt-1.5">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
