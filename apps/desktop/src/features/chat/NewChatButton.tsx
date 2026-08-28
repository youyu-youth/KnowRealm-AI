import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MessageSquarePlus } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";

type NewChatButtonProps = {
  labelKey?: string;
  variant?: "default" | "outline";
};

export function NewChatButton({
  labelKey = "chat.newSession",
  variant = "default",
}: NewChatButtonProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState("");

  const createSession = useMutation({
    mutationFn: () => chatApi.create(),
    onSuccess: async (session) => {
      await queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      await navigate({
        to: "/chat/$sessionId",
        params: { sessionId: session.id },
      });
    },
    onError: (createError: Error) => {
      setError(createError.message);
    },
  });

  return (
    <div className="flex flex-col gap-2">
      <Button
        variant={variant}
        onClick={() => {
          setError("");
          createSession.mutate();
        }}
        disabled={createSession.isPending}
      >
        {createSession.isPending ? (
          <Spinner data-icon="inline-start" aria-label={t("chat.creating")} />
        ) : (
          <MessageSquarePlus data-icon="inline-start" aria-hidden="true" />
        )}
        {t(labelKey)}
      </Button>
      {error ? (
        <Alert variant="destructive" className="w-auto">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
