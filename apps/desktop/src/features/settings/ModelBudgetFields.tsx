import type { components } from "@knowrealm/api-types";
import { useTranslation } from "react-i18next";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
  FieldDescription,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { openWebUrl } from "@/services/tauri/webLinks";
import { appToast } from "@/components/common/appToastManager";

type Provider = components["schemas"]["LlmProviderOut"];
const FIELDS = [
  "input_limit",
  "context_window",
  "max_output",
  "answer_output",
  "summary_output",
] as const;

export function ModelBudgetFields({
  initial,
  disabled,
}: {
  initial: Provider | null;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  return (
    <FieldSet>
      <FieldLegend>{t("settings.modelBudget.title")}</FieldLegend>
      <FieldDescription>{t("settings.modelBudget.hint")}</FieldDescription>
      <FieldGroup className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {FIELDS.map((key) => {
          const effective = initial?.capability?.[key];
          const source = initial?.capability?.sources?.[key];
          return (
            <Field key={key}>
              <FieldLabel htmlFor={`model-budget-${key}`}>
                {t(`settings.modelBudget.${key}`)}
              </FieldLabel>
              <Input
                id={`model-budget-${key}`}
                name={key}
                type="number"
                min={1}
                max={100000000}
                step={1}
                defaultValue={
                  initial?.model_budget?.[key] ??
                  (key === "answer_output"
                    ? 4096
                    : key === "summary_output"
                      ? 1024
                      : "")
                }
                placeholder={
                  effective != null
                    ? String(effective)
                    : t("settings.modelBudget.unknown")
                }
                required={key === "answer_output" || key === "summary_output"}
                disabled={disabled}
              />
              {source ? (
                <FieldDescription>
                  {source === "USER" ? (
                    t("settings.modelBudget.userSource")
                  ) : (
                    <a
                      href={source}
                      onClick={(event) => {
                        event.preventDefault();
                        void openWebUrl(source).catch(() =>
                          appToast.add({
                            description: t(
                              "settings.modelBudget.openSourceFailed",
                            ),
                          }),
                        );
                      }}
                      target="_blank"
                      rel="noreferrer"
                      className="underline underline-offset-4"
                    >
                      {t("settings.modelBudget.officialSource", {
                        count: effective,
                      })}
                    </a>
                  )}
                </FieldDescription>
              ) : null}
            </Field>
          );
        })}
      </FieldGroup>
    </FieldSet>
  );
}
