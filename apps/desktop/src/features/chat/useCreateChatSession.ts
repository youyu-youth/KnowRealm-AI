import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";
import type { ChatSessionCreate } from "@/features/chat/api/types";

/** 创建会话并跳转：范围切换（胶囊 / 新建菜单 / 课程详情 CTA）共用的统一入口。 */
export function useCreateChatSession() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ChatSessionCreate) => chatApi.create(payload),
    onSuccess: async (session) => {
      await queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      await navigate({
        to: "/chat/$sessionId",
        params: { sessionId: session.id },
      });
    },
  });
}
