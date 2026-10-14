import type { components } from "@knowrealm/api-types";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";
import { useRecordHotkeys } from "react-hotkeys-hook";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldLabel } from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import { TabsContent } from "@/components/ui/tabs";
import { isUiLanguage, UI_LANGUAGES } from "@/i18n/language";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";
import { ThemeChoices } from "@/features/settings/ThemeChoices";
import { useSavePreference } from "@/features/settings/useSavePreference";
import {
  SettingsChoiceRow,
  SettingsPanelHeader,
  SettingsRow,
} from "@/features/settings/SettingsLayout";
import { normalizeRecordedKeys } from "@/features/settings/shortcutAccelerator";
import { TimezoneCombobox } from "@/features/settings/TimezoneCombobox";
import {
  rebindQuickNoteShortcut,
  setAutostart,
} from "@/services/tauri/preferences";

type PreferencesOut = components["schemas"]["PreferencesOut"];

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

export function PreferencesSection() {
  const { t } = useTranslation();
  const preferences = useQuery({
    queryKey: settingsKeys.preferences,
    queryFn: settingsApi.getPreferences,
  });

  const panel = (id: string, title: string, content: ReactNode) => (
    <section aria-labelledby={id} className="max-w-5xl">
      <SettingsPanelHeader id={id} title={title} />
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
        <div className="mt-8">{content}</div>
      )}
    </section>
  );

  return (
    <>
      <TabsContent value="appearance" keepMounted className="min-w-0">
        {panel(
          "settings-appearance-title",
          t("settings.navigation.appearance"),
          preferences.data ? (
            <AppearancePreferences preferences={preferences.data} />
          ) : null,
        )}
      </TabsContent>
      <TabsContent value="desktop" keepMounted className="min-w-0">
        {panel(
          "settings-desktop-title",
          t("settings.preferences.desktopTitle"),
          preferences.data ? (
            <DesktopBehaviorPreferences preferences={preferences.data} />
          ) : null,
        )}
      </TabsContent>
      <TabsContent value="general" keepMounted className="min-w-0">
        {panel(
          "settings-general-title",
          t("settings.navigation.general"),
          preferences.data ? (
            <GeneralPreferences preferences={preferences.data} />
          ) : null,
        )}
      </TabsContent>
    </>
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
  const language = useSavePreference();
  const layout = useSavePreference();

  return (
    <div className="flex flex-col gap-7">
      <SettingsChoiceRow label={t("settings.preferences.languageLegend")}>
        <RadioGroup
          className="flex flex-wrap gap-x-5 gap-y-3"
          value={preferences.language}
          onValueChange={(value) => {
            if (isUiLanguage(value)) language.mutate({ language: value });
          }}
          disabled={language.isPending}
        >
          {UI_LANGUAGES.map((item) => {
            const id = `preference-language-${item}`;
            return (
              <Field key={id} orientation="horizontal" className="w-auto">
                <RadioGroupItem id={id} value={item} />
                <FieldLabel htmlFor={id}>
                  {t(`settings.preferences.language.${item}`)}
                </FieldLabel>
              </Field>
            );
          })}
        </RadioGroup>
        <SaveError error={language.error} />
      </SettingsChoiceRow>

      <SettingsChoiceRow label={t("settings.preferences.themeLegend")}>
        <RadioGroup
          className="flex flex-wrap gap-x-5 gap-y-3"
          value={
            theme.status === "pending"
              ? (theme.variables?.theme ?? preferences.theme)
              : preferences.theme
          }
          onValueChange={(value) => {
            if (isTheme(value)) theme.mutate({ theme: value });
          }}
          disabled={theme.isPending}
        >
          {THEMES.map((item) => {
            const id = `preference-theme-${item}`;
            return (
              <Field key={id} orientation="horizontal" className="w-auto">
                <RadioGroupItem id={id} value={item} />
                <FieldLabel htmlFor={id}>
                  {t(`settings.preferences.theme.${item}`)}
                </FieldLabel>
              </Field>
            );
          })}
        </RadioGroup>
        <SaveError
          error={theme.error}
          onRetry={() => theme.variables && theme.mutate(theme.variables)}
        />
      </SettingsChoiceRow>

      <ThemeChoices mode="LIGHT" preferences={preferences} />
      <ThemeChoices mode="DARK" preferences={preferences} />

      <SettingsChoiceRow label={t("settings.preferences.layoutLegend")}>
        <RadioGroup
          className="flex flex-wrap gap-x-5 gap-y-3"
          value={preferences.layout_mode ?? "SIDEBAR"}
          onValueChange={(value) => {
            if (value === "SIDEBAR" || value === "TOP")
              layout.mutate({ layout_mode: value });
          }}
          disabled={layout.isPending}
        >
          {(["SIDEBAR", "TOP"] as const).map((item) => {
            const id = `preference-layout-${item}`;
            return (
              <Field key={id} orientation="horizontal" className="w-auto">
                <RadioGroupItem id={id} value={item} />
                <FieldLabel htmlFor={id}>
                  {t(`settings.preferences.layout.${item}`)}
                </FieldLabel>
              </Field>
            );
          })}
        </RadioGroup>
        <SaveError
          error={layout.error}
          onRetry={() => layout.variables && layout.mutate(layout.variables)}
        />
      </SettingsChoiceRow>

      <SettingsChoiceRow label={t("settings.preferences.fontScaleLegend")}>
        <RadioGroup
          className="flex flex-wrap gap-x-5 gap-y-3"
          value={preferences.font_scale}
          onValueChange={(value) => {
            if (isFontScale(value)) fontScale.mutate({ font_scale: value });
          }}
          disabled={fontScale.isPending}
        >
          {FONT_SCALES.map((item) => {
            const id = `preference-font-scale-${item}`;
            return (
              <Field key={id} orientation="horizontal" className="w-auto">
                <RadioGroupItem id={id} value={item} />
                <FieldLabel htmlFor={id}>
                  {t(`settings.preferences.fontScale.${item}`)}
                </FieldLabel>
              </Field>
            );
          })}
        </RadioGroup>
        <SaveError error={fontScale.error} />
      </SettingsChoiceRow>
    </div>
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
    <div className="flex flex-col gap-7">
      <SettingsChoiceRow label={t("settings.preferences.closeBehaviorLegend")}>
        <RadioGroup
          className="flex flex-wrap gap-x-5 gap-y-3"
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
              <Field key={id} orientation="horizontal" className="w-auto">
                <RadioGroupItem id={id} value={item} />
                <FieldLabel htmlFor={id}>
                  {t(`settings.preferences.closeBehavior.${item}`)}
                </FieldLabel>
              </Field>
            );
          })}
        </RadioGroup>
        <SaveError error={closeBehavior.error} />
      </SettingsChoiceRow>

      <SettingsRow
        label={t("settings.preferences.autostartLabel")}
        htmlFor="preference-autostart"
      >
        <Field orientation="horizontal" className="min-h-8">
          <Checkbox
            id="preference-autostart"
            checked={preferences.autostart}
            onCheckedChange={toggleAutostart}
            disabled={autostart.isPending}
          />
          <p className="text-label text-muted-foreground">
            {preferences.autostart
              ? t("settings.preferences.enabled")
              : t("settings.preferences.disabled")}
          </p>
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
      </SettingsRow>

      <QuickNoteShortcutField preferences={preferences} />
    </div>
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
    <SettingsRow
      label={t("settings.preferences.shortcutLabel")}
      htmlFor="preference-quick-note-shortcut"
    >
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
    </SettingsRow>
  );
}

function GeneralPreferences({ preferences }: { preferences: PreferencesOut }) {
  const { t } = useTranslation();
  const timezone = useSavePreference();
  const quizCount = useSavePreference();

  return (
    <div className="flex flex-col gap-7">
      <SettingsRow
        label={t("settings.preferences.timezoneLabel")}
        htmlFor="preference-timezone"
      >
        <TimezoneCombobox
          id="preference-timezone"
          value={preferences.timezone}
          onSelect={(value) => timezone.mutate({ timezone: value })}
          disabled={timezone.isPending}
        />
        <SaveError error={timezone.error} />
      </SettingsRow>

      <SettingsChoiceRow label={t("settings.preferences.quizCountLegend")}>
        <RadioGroup
          className="flex flex-wrap gap-x-5 gap-y-3"
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
              <Field key={id} orientation="horizontal" className="w-auto">
                <RadioGroupItem id={id} value={String(count)} />
                <FieldLabel htmlFor={id}>{count}</FieldLabel>
              </Field>
            );
          })}
        </RadioGroup>
        <SaveError error={quizCount.error} />
      </SettingsChoiceRow>
    </div>
  );
}

function SaveError({
  error,
  onRetry,
}: {
  error: Error | null;
  onRetry?: () => void;
}) {
  const { t } = useTranslation();
  if (!error) return null;
  return (
    <Alert variant="destructive" className="w-auto">
      <AlertDescription>{error.message}</AlertDescription>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          {t("settings.preferences.retry")}
        </Button>
      ) : null}
    </Alert>
  );
}
