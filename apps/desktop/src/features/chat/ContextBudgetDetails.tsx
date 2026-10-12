import type { components } from "@knowrealm/api-types";
import { useTranslation } from "react-i18next";
import { openWebUrl } from "@/services/tauri/webLinks";
import { appToast } from "@/components/common/appToastManager";

export function ContextBudgetDetails({
  estimate,
}: {
  estimate: components["schemas"]["InputEstimate"];
}) {
  const { t, i18n } = useTranslation();
  const number = (value: number | null | undefined) =>
    value == null
      ? t("chat.contextView.unknown")
      : value.toLocaleString(i18n.language);
  const capability = estimate.policy.capability;
  const metrics = [
    ["inputTokens", estimate.input_tokens],
    ["usableBudget", estimate.usable_budget],
    ["outputReserve", estimate.output_reserve],
    ["safetyMargin", estimate.safety_margin],
    ["remaining", estimate.remaining],
    ["input_limit", capability.input_limit],
    ["context_window", capability.context_window],
    ["max_output", capability.max_output],
  ] as const;
  return (
    <div className="min-w-0">
      <p className="text-body text-ink break-words">{estimate.policy.model}</p>
      <p className="text-label text-muted-foreground mt-1 break-all">
        {estimate.policy.base_url}
      </p>
      <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 tabular-nums lg:grid-cols-4">
        {metrics.map(([key, value]) => (
          <div key={key}>
            <dt className="text-label text-muted-foreground">
              {t(`chat.contextView.${key}`)}
            </dt>
            <dd className="text-body text-ink mt-1">{number(value)}</dd>
          </div>
        ))}
      </dl>
      <p className="text-label text-muted-foreground mt-5">
        {t("chat.contextView.approximate", { tokenizer: estimate.tokenizer })}
      </p>
      <p className="text-label text-muted-foreground mt-2">
        {t("chat.contextView.inventory", {
          messages: estimate.message_count,
          tools: estimate.tool_count,
        })}
      </p>
      <dl className="text-label text-muted-foreground mt-3 flex flex-wrap gap-x-5 gap-y-2 tabular-nums">
        {Object.entries(estimate.components).map(([key, value]) => (
          <div className="flex gap-2" key={key}>
            <dt>{t(`chat.contextView.components.${key}`)}</dt>
            <dd>{number(value)}</dd>
          </div>
        ))}
      </dl>
      <ul className="text-label text-muted-foreground mt-4 flex flex-col gap-1">
        {(["input_limit", "context_window", "max_output"] as const).map(
          (key) => {
            const source = capability.sources?.[key];
            return (
              <li key={key} className="break-words">
                {t(`chat.contextView.${key}`)} ·{" "}
                {source === "USER" ? (
                  t("settings.modelBudget.userSource")
                ) : source ? (
                  <a
                    className="underline underline-offset-4"
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
                  >
                    {t("settings.modelBudget.officialSourceLabel")}
                  </a>
                ) : (
                  t("chat.contextView.unknown")
                )}
              </li>
            );
          },
        )}
      </ul>
    </div>
  );
}
