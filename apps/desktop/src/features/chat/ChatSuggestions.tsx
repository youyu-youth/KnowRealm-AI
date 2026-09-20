import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";

const SUGGESTIONS = [
  {
    id: "explain",
    titleKey: "chat.suggestions.explain.title",
    descriptionKey: "chat.suggestions.explain.description",
    promptKey: "chat.suggestions.explain.prompt",
  },
  {
    id: "quiz",
    titleKey: "chat.suggestions.quiz.title",
    descriptionKey: "chat.suggestions.quiz.description",
    promptKey: "chat.suggestions.quiz.prompt",
  },
  {
    id: "sources",
    titleKey: "chat.suggestions.sources.title",
    descriptionKey: "chat.suggestions.sources.description",
    promptKey: "chat.suggestions.sources.prompt",
  },
] as const;

const RESEARCH_SUGGESTIONS = [
  {
    id: "researchCompare",
    titleKey: "chat.researchSuggestions.compare.title",
    descriptionKey: "chat.researchSuggestions.compare.description",
    promptKey: "chat.researchSuggestions.compare.prompt",
  },
  {
    id: "researchConflict",
    titleKey: "chat.researchSuggestions.conflict.title",
    descriptionKey: "chat.researchSuggestions.conflict.description",
    promptKey: "chat.researchSuggestions.conflict.prompt",
  },
  {
    id: "researchSurvey",
    titleKey: "chat.researchSuggestions.survey.title",
    descriptionKey: "chat.researchSuggestions.survey.description",
    promptKey: "chat.researchSuggestions.survey.prompt",
  },
] as const;

type ChatSuggestionsProps = {
  onPick: (prompt: string) => void;
  /** 研究会话换研究特化示例（研究会话 V1）。 */
  research?: boolean;
};

/** 空会话的提问建议（文案为向导示意，点击后填入输入框，可自由修改再发送）。 */
export function ChatSuggestions({
  onPick,
  research = false,
}: ChatSuggestionsProps) {
  const { t } = useTranslation();
  const suggestions = research ? RESEARCH_SUGGESTIONS : SUGGESTIONS;
  return (
    <section className="pt-6">
      <p className="text-body-dense text-muted-foreground">
        {research
          ? t("chat.researchSuggestions.title")
          : t("chat.suggestions.title")}
      </p>
      <div className="mt-3 grid gap-2 lg:grid-cols-3">
        {suggestions.map((suggestion) => (
          <button
            key={suggestion.id}
            type="button"
            onClick={() => onPick(t(suggestion.promptKey))}
            className="group border-border-subtle bg-surface-raised hover:border-border-strong hover:bg-surface-subtle focus-visible:ring-ring/40 flex items-start justify-between gap-2 rounded-xl border px-4 py-3 text-start transition-colors focus-visible:ring-3"
          >
            <span className="min-w-0">
              <span className="text-body-dense text-ink block font-medium">
                {t(suggestion.titleKey)}
              </span>
              <span className="text-label text-muted-foreground mt-0.5 block">
                {t(suggestion.descriptionKey)}
              </span>
            </span>
            <ChevronRight
              className="text-muted-foreground group-hover:text-ink size-4 shrink-0 transition-transform group-hover:translate-x-0.5"
              aria-hidden="true"
            />
          </button>
        ))}
      </div>
    </section>
  );
}
