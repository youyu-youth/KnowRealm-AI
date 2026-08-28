import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type ChatComposerProps = {
  disabled: boolean;
  isStreaming: boolean;
  onSend: (content: string) => void;
  onStop: () => void;
};

const MESSAGE_MAX_LENGTH = 8000;

export function ChatComposer({
  disabled,
  isStreaming,
  onSend,
  onStop,
}: ChatComposerProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");

  function submit() {
    const content = value.trim();
    if (!content || disabled || isStreaming) return;
    onSend(content);
    setValue("");
  }

  return (
    <form
      className="border-border flex items-end gap-2 border-t pt-4"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <Textarea
        value={value}
        rows={2}
        maxLength={MESSAGE_MAX_LENGTH}
        placeholder={t("chat.inputPlaceholder")}
        aria-label={t("chat.inputLabel")}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          // Enter 发送、Shift+Enter 换行。
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
      />
      {isStreaming ? (
        <Button type="button" variant="outline" onClick={onStop}>
          <Square data-icon="inline-start" aria-hidden="true" />
          {t("chat.stop")}
        </Button>
      ) : (
        <Button type="submit" disabled={disabled}>
          <Send data-icon="inline-start" aria-hidden="true" />
          {t("chat.send")}
        </Button>
      )}
    </form>
  );
}
