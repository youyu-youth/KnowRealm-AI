import type { components } from "@knowrealm/api-types";
import {
  useIsMutating,
  useMutation,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { settingsApi } from "@/features/settings/api/settings";
import { settingsKeys } from "@/features/settings/api/keys";
import {
  applyTheme,
  normalizeAppearance,
} from "@/features/settings/appearance";
import { confirmAppearance } from "@/features/settings/appearanceCache";

type PreferencesOut = components["schemas"]["PreferencesOut"];
type PreferencesUpdate = components["schemas"]["PreferencesUpdate"];
const writing = new WeakSet<QueryClient>();
const mutationKey = [...settingsKeys.preferences, "save"];

export function useSavePreference() {
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const busy = useIsMutating({ mutationKey }) > 0;
  const mutation = useMutation({
    mutationKey,
    mutationFn: async (patch: PreferencesUpdate) => {
      if (writing.has(queryClient))
        throw new Error(t("settings.preferences.saveBusy"));
      writing.add(queryClient);
      const confirmed = queryClient.getQueryData<PreferencesOut>(
        settingsKeys.preferences,
      );
      try {
        await queryClient.cancelQueries({ queryKey: settingsKeys.preferences });
        if (
          confirmed &&
          ("theme" in patch ||
            "light_theme_id" in patch ||
            "dark_theme_id" in patch)
        ) {
          const candidate = normalizeAppearance({ ...confirmed, ...patch });
          applyTheme(candidate.theme, candidate);
        }
        const data = await settingsApi.updatePreferences(patch);
        await queryClient.cancelQueries({ queryKey: settingsKeys.preferences });
        queryClient.setQueryData(settingsKeys.preferences, data);
        confirmAppearance(data);
        return data;
      } catch (error) {
        if (confirmed) confirmAppearance(confirmed);
        // HTTP 失败也可能已经提交：读回权威事实，失败则保留最后确认值。
        try {
          await queryClient.cancelQueries({
            queryKey: settingsKeys.preferences,
          });
          const data = await settingsApi.getPreferences();
          await queryClient.cancelQueries({
            queryKey: settingsKeys.preferences,
          });
          queryClient.setQueryData(settingsKeys.preferences, data);
          confirmAppearance(data);
        } catch {
          // 保留原错误及确认值，控件仍可重试。
        }
        throw error;
      } finally {
        writing.delete(queryClient);
      }
    },
  });
  return { ...mutation, isPending: busy || mutation.isPending };
}
