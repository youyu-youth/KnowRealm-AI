import type { components } from "@knowrealm/api-types";
import { useTranslation } from "react-i18next";

export function PracticeSourceList({
  sources,
}: {
  sources: components["schemas"]["PracticeSourceOut"][];
}) {
  const { t } = useTranslation();
  return (
    <ul className="text-body space-y-1">
      {sources.map((source) => (
        <li key={source.record_id}>
          {source.title} ·{" "}
          {t("practice.related", { count: source.related_count })}
          {source.matching_basis?.length ? (
            <span>
              {" "}
              ·{" "}
              {source.matching_basis
                .map((reason) => t(`practice.basis.${reason}`))
                .join(" · ")}
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
