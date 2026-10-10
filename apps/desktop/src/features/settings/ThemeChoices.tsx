import type { components } from "@knowrealm/api-types";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import { APPEARANCE_THEMES } from "@/features/settings/appearance";
import { SettingsChoiceRow } from "@/features/settings/SettingsLayout";
import { useSavePreference } from "@/features/settings/useSavePreference";

export function ThemeChoices({
  mode,
  preferences,
}: {
  mode: "LIGHT" | "DARK";
  preferences: components["schemas"]["PreferencesOut"];
}) {
  const { t } = useTranslation();
  const save = useSavePreference();
  const field = mode === "LIGHT" ? "light_theme_id" : "dark_theme_id";
  const candidate =
    save.status === "pending" ? save.variables?.[field] : undefined;
  const value = candidate ?? preferences[field];
  const label = t(`settings.preferences.themeGroups.${mode}`);
  return (
    <SettingsChoiceRow label={label}>
      <RadioGroup
        aria-label={label}
        className="grid grid-cols-1 gap-4 sm:grid-cols-2"
        value={value}
        disabled={save.isPending}
        onValueChange={(id) => {
          if (mode === "LIGHT") {
            const theme = APPEARANCE_THEMES.LIGHT.find(
              (item) => item.id === id,
            );
            if (theme) save.mutate({ light_theme_id: theme.id });
          } else {
            const theme = APPEARANCE_THEMES.DARK.find((item) => item.id === id);
            if (theme) save.mutate({ dark_theme_id: theme.id });
          }
        }}
      >
        {APPEARANCE_THEMES[mode].map(({ id, preview }) => (
          <Field key={id} data-disabled={save.isPending}>
            <FieldLabel
              htmlFor={`appearance-${id}`}
              className="min-w-0 flex-col items-stretch gap-3"
            >
              <div
                aria-hidden="true"
                className="border-input flex h-20 overflow-hidden rounded-md border"
                style={{ background: preview[0] }}
              >
                <span className="w-1/4" style={{ background: preview[0] }} />
                <span
                  className="flex flex-1 flex-col gap-2 p-3"
                  style={{ background: preview[1] }}
                >
                  <span
                    className="h-2 w-2/3 rounded-sm"
                    style={{ background: preview[3] }}
                  />
                  <span
                    className="h-6 rounded-sm"
                    style={{
                      background: preview[2],
                      border: `1px solid ${preview[3]}40`,
                    }}
                  />
                </span>
              </div>
              <span className="flex min-w-0 items-center gap-2">
                <RadioGroupItem id={`appearance-${id}`} value={id} />
                <span>{t(`settings.preferences.themeNames.${id}`)}</span>
              </span>
            </FieldLabel>
          </Field>
        ))}
      </RadioGroup>
      {save.status === "pending" && save.variables?.[field] ? (
        <p
          role="status"
          className="text-label text-muted-foreground mt-3 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("settings.preferences.savingTheme")}
        </p>
      ) : null}
      {save.error ? (
        <Alert variant="destructive" className="mt-3">
          <AlertDescription>
            {t("settings.preferences.themeSaveFailed")}
          </AlertDescription>
          <Button
            variant="outline"
            size="sm"
            disabled={save.isPending}
            onClick={() => save.variables && save.mutate(save.variables)}
          >
            {t("settings.preferences.retry")}
          </Button>
        </Alert>
      ) : null}
    </SettingsChoiceRow>
  );
}
