import type { components } from "@knowrealm/api-types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useCallback, useEffect, useState } from "react";
import { useRecordHotkeys } from "react-hotkeys-hook";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldLabel, FieldLegend } from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";
import { normalizeRecordedKeys } from "@/features/settings/shortcutAccelerator";
import { TimezoneCombobox } from "@/features/settings/TimezoneCombobox";
import {
  rebindQuickNoteShortcut,
  setAutostart,
} from "@/services/tauri/preferences";

type PreferencesOut = components["schemas"]["PreferencesOut"];
type PreferencesUpdate = components["schemas"]["PreferencesUpdate"];

const THEMES = ["LIGHT", "DARK", "SYSTEM"] as const;
const FONT_SCALES = ["S", "M", "L"] as const;
const CLOSE_BEHAVIORS = ["TRAY", "EXIT"] as const;
const QUIZ_COUNT_CHOICES = [3, 5, 10] as const;

function isTheme(value: string): value is (typeof THEMES)[number] {
  return (THEMES as readonly string[]).includes(value);
}

function isCloseBehavior(
  value: string,
): value is (typeof CLOSE_BEHAVIORS)[number] {
  return (CLOSE_BEHAVIORS as readonly string[]).includes(value);
}

function isFontScale(value: string): value is (typeof FONT_SCALES)[number] {
  return (FONT_SCALES as readonly string[]).includes(value);
}

// 控件值一律绑定服务端事实：改动即 PUT，成功后以全量响应写回缓存；
// 失败不改缓存，控件自然停留在当前生效值，配合行内报错即「回显服务端事实」。
function useSavePreference() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: PreferencesUpdate) =>
      settingsApi.updatePreferences(patch),
    onSuccess: (data) =>
      queryClient.setQueryData(settingsKeys.preferences, data),
  });
}

export function PreferencesSection() {
  const { t } = useTranslation();
  const preferences = useQuery({
    queryKey: settingsKeys.preferences,
    queryFn: settingsApi.getPreferences,
  });

  return (
    <div className="border-border max-w-reading mt-8 border-t pt-8">
      <h2 className="text-section font-section text-ink">
        {t("settings.preferences.sectionTitle")}
      </h2>
      <p className="max-w-reading text-body text-muted-foreground">
        {t("settings.preferences.sectionDescription")}
      </p>
      {preferences.isPending ? (
        <p
          role="status"
          className="text-body text-muted-foreground mt-6 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("settings.preferences.loading")}
        </p>
      ) : preferences.isError ? (
        <div className="mt-6">
          <p className="max-w-reading text-body text-muted-foreground">
            {preferences.error.message}
          </p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => void preferences.refetch()}
          >
            {t("settings.preferences.retry")}
          </Button>
        </div>
      ) : (
        <div className="mt-6 flex flex-col gap-8">
          <AppearancePreferences preferences={preferences.data} />
          <DesktopBehaviorPreferences preferences={preferences.data} />
          <GeneralPreferences preferences={preferences.data} />
        </div>
      )}
    </div>
  );
}

function AppearancePreferences({
  preferences,
}: {
  preferences: PreferencesOut;
}) {
  const { t } = useTranslation();
  const theme = useSavePreference();
  const fontScale = useSavePreference();

  return (
    <section aria-labelledby="preferences-appearance-title">
      <h3
        id="preferences-appearance-title"
        className="text-section font-section text-ink"
      >
        {t("settings.preferences.appearanceTitle")}
      </h3>
      <div className="mt-4 flex flex-col gap-5">
        <Field>
          <FieldLegend variant="label">
            {t("settings.preferences.themeLegend")}
          </FieldLegend>
          <RadioGroup
            value={preferences.theme}
            onValueChange={(value) => {
              if (isTheme(value)) theme.mutate({ theme: value });
            }}
            disabled={theme.isPending}
          >
            {THEMES.map((item) => {
              const id = `preference-theme-${item}`;
              return (
                <Field key={id} orientation="horizontal">
                  <RadioGroupItem id={id} value={item} />
                  <FieldLabel htmlFor={id}>
                    {t(`settings.preferences.theme.${item}`)}
                  </FieldLabel>
                </Field>
              );
            })}
          </RadioGroup>
          <SaveError error={theme.error} />
        </Field>

        <Field>
          <FieldLegend variant="label">
            {t("settings.preferences.fontScaleLegend")}
          </FieldLegend>
          <RadioGroup
            value={preferences.font_scale}
            onValueChange={(value) => {
              if (isFontScale(value)) fontScale.mutate({ font_scale: value });
            }}
            disabled={fontScale.isPending}
          >
            {FONT_SCALES.map((item) => {
              const id = `preference-font-scale-${item}`;
              return (
                <Field key={id} orientation="horizontal">
                  <RadioGroupItem id={id} value={item} />
                  <FieldLabel htmlFor={id}>
                    {t(`settings.preferences.fontScale.${item}`)}
                  </FieldLabel>
                </Field>
              );
            })}
          </RadioGroup>
          <SaveError error={fontScale.error} />
        </Field>
      </div>
    </section>
  );
}

function DesktopBehaviorPreferences({
  preferences,
}: {
  preferences: PreferencesOut;
}) {
  const { t } = useTranslation();
  const closeBehavior = useSavePreference();
  const autostart = useSavePreference();
  const [autostartOsError, setAutostartOsError] = useState(false);

  // 先写 OS 启动项再持久化偏好：OS 写入失败即报错、不动偏好，开关显示即真实生效；
  // 偏好保存失败回显服务端事实，OS 与偏好间的漂移不做启动对账。
  const toggleAutostart = (checked: boolean) => {
    setAutostartOsError(false);
    void setAutostart(checked)
      .then(() => autostart.mutate({ autostart: checked }))
      .catch(() => setAutostartOsError(true));
  };

  return (
    <section aria-labelledby="preferences-desktop-title">
      <h3
        id="preferences-desktop-title"
        className="text-section font-section text-ink"
      >
        {t("settings.preferences.desktopTitle")}
      </h3>
      <div className="mt-4 flex flex-col gap-5">
        <Field>
          <FieldLegend variant="label">
            {t("settings.preferences.closeBehaviorLegend")}
          </FieldLegend>
          <RadioGroup
            value={preferences.close_behavior}
            onValueChange={(value) => {
              if (isCloseBehavior(value))
                closeBehavior.mutate({ close_behavior: value });
            }}
            disabled={closeBehavior.isPending}
          >
            {CLOSE_BEHAVIORS.map((item) => {
              const id = `preference-close-behavior-${item}`;
              return (
                <Field key={id} orientation="horizontal">
                  <RadioGroupItem id={id} value={item} />
                  <FieldLabel htmlFor={id}>
                    {t(`settings.preferences.closeBehavior.${item}`)}
                  </FieldLabel>
                </Field>
              );
            })}
          </RadioGroup>
          <SaveError error={closeBehavior.error} />
        </Field>

        <Field>
          <Field orientation="horizontal">
            <Checkbox
              id="preference-autostart"
              checked={preferences.autostart}
              onCheckedChange={toggleAutostart}
              disabled={autostart.isPending}
            />
            <FieldLabel htmlFor="preference-autostart">
              {t("settings.preferences.autostartLabel")}
            </FieldLabel>
          </Field>
          {autostartOsError ? (
            <Alert variant="destructive" className="w-auto">
              <AlertDescription>
                {t("settings.preferences.autostartOsFailed")}
              </AlertDescription>
            </Alert>
          ) : (
            <SaveError error={autostart.error} />
          )}
        </Field>

        <QuickNoteShortcutField preferences={preferences} />
      </div>
    </section>
  );
}

type ShortcutFieldError =
  | "conflict"
  | "persist-failed"
  | "failed"
  | "missing-modifier"
  | "unsupported-key";

const SHORTCUT_ERROR_KEYS: Record<ShortcutFieldError, string> = {
  conflict: "settings.preferences.shortcutConflict",
  "persist-failed": "settings.preferences.shortcutRebindFailed",
  failed: "settings.preferences.shortcutRebindFailed",
  "missing-modifier": "settings.preferences.shortcutMissingModifier",
  "unsupported-key": "settings.preferences.shortcutUnsupportedKey",
};

function QuickNoteShortcutField({
  preferences,
}: {
  preferences: PreferencesOut;
}) {
  const { t } = useTranslation();
  const save = useSavePreference();
  const [shortcutError, setShortcutError] = useState<ShortcutFieldError | null>(
    null,
  );
  const [keys, { start, stop, resetKeys, isRecording }] = useRecordHotkeys();

  const stopRecording = useCallback(() => {
    stop();
    resetKeys();
  }, [stop, resetKeys]);

  // 输入法组合输入防呆与 Esc 取消：capture 阶段拦截，
  // 让 document 冒泡阶段的 useRecordHotkeys 监听收不到这些按键。
  useEffect(() => {
    if (!isRecording) return;
    const guard = (event: KeyboardEvent) => {
      if (!event.isComposing && event.code !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      if (event.code === "Escape") stopRecording();
    };
    window.addEventListener("keydown", guard, { capture: true });
    return () =>
      window.removeEventListener("keydown", guard, { capture: true });
  }, [isRecording, stopRecording]);

  // 按下即录：修饰键先按、主键收尾即组合完成，立即进入改键时序。
  // 收尾放进微任务，避免 effect 内同步 setState 触发级联渲染。
  useEffect(() => {
    if (!isRecording) return;
    const result = normalizeRecordedKeys(keys);
    if (result.status === "waiting") return;
    queueMicrotask(() => {
      stopRecording();
      if (result.status === "invalid") {
        setShortcutError(result.reason);
        return;
      }
      setShortcutError(null);
      void rebindQuickNoteShortcut(result.accelerator, () =>
        save.mutateAsync({ quick_note_shortcut: result.accelerator }),
      ).then((rebind) => {
        if (!rebind.ok) setShortcutError(rebind.reason);
      });
    });
  }, [keys, isRecording, save, stopRecording]);

  return (
    <Field>
      <FieldLabel htmlFor="preference-quick-note-shortcut">
        {t("settings.preferences.shortcutLabel")}
      </FieldLabel>
      <div className="flex flex-wrap items-center gap-3">
        {isRecording ? (
          <>
            <p role="status" className="text-body text-muted-foreground">
              {t("settings.preferences.shortcutRecording")}
            </p>
            <Button variant="ghost" size="sm" onClick={stopRecording}>
              {t("settings.preferences.shortcutCancel")}
            </Button>
          </>
        ) : (
          <>
            <code
              id="preference-quick-note-shortcut"
              className="bg-surface-subtle text-body rounded-md px-2 py-1"
            >
              {preferences.quick_note_shortcut}
            </code>
            <Button
              variant="outline"
              size="sm"
              disabled={save.isPending}
              onClick={() => {
                setShortcutError(null);
                start();
              }}
            >
              {t("settings.preferences.shortcutChange")}
            </Button>
          </>
        )}
      </div>
      {shortcutError ? (
        <Alert variant="destructive" className="w-auto">
          <AlertDescription>
            {t(SHORTCUT_ERROR_KEYS[shortcutError])}
          </AlertDescription>
        </Alert>
      ) : null}
    </Field>
  );
}

function GeneralPreferences({ preferences }: { preferences: PreferencesOut }) {
  const { t } = useTranslation();
  const timezone = useSavePreference();
  const quizCount = useSavePreference();

  return (
    <section aria-labelledby="preferences-general-title">
      <h3
        id="preferences-general-title"
        className="text-section font-section text-ink"
      >
        {t("settings.preferences.generalTitle")}
      </h3>
      <div className="mt-4 flex flex-col gap-5">
        <Field>
          <FieldLabel htmlFor="preference-timezone">
            {t("settings.preferences.timezoneLabel")}
          </FieldLabel>
          <TimezoneCombobox
            id="preference-timezone"
            value={preferences.timezone}
            onSelect={(value) => timezone.mutate({ timezone: value })}
            disabled={timezone.isPending}
          />
          <SaveError error={timezone.error} />
        </Field>

        <Field>
          <FieldLegend variant="label">
            {t("settings.preferences.quizCountLegend")}
          </FieldLegend>
          <RadioGroup
            value={String(preferences.quiz_last_count)}
            onValueChange={(value) => {
              const next = Number(value);
              if ((QUIZ_COUNT_CHOICES as readonly number[]).includes(next)) {
                quizCount.mutate({ quiz_last_count: next as 3 | 5 | 10 });
              }
            }}
            disabled={quizCount.isPending}
          >
            {QUIZ_COUNT_CHOICES.map((count) => {
              const id = `preference-quiz-count-${count}`;
              return (
                <Field key={id} orientation="horizontal">
                  <RadioGroupItem id={id} value={String(count)} />
                  <FieldLabel htmlFor={id}>{count}</FieldLabel>
                </Field>
              );
            })}
          </RadioGroup>
          <SaveError error={quizCount.error} />
        </Field>
      </div>
    </section>
  );
}

function SaveError({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <Alert variant="destructive" className="w-auto">
      <AlertDescription>{error.message}</AlertDescription>
    </Alert>
  );
}
