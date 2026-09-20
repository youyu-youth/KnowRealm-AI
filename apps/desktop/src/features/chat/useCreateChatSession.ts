import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";
import type { ChatSessionCreate } from "@/features/chat/api/types";

/** 创建会话请求体；研究会话额外携带研究问题（经 ?prompt= 预填输入框）。 */
export type CreateChatSessionInput = ChatSessionCreate & { prompt?: string };

/** 创建会话并跳转：范围切换（胶囊 / 新建菜单 / 课程详情 CTA）共用的统一入口。 */
export function useCreateChatSession() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ prompt, ...body }: CreateChatSessionInput) => {
      // prompt 只在前端消费（?prompt= 预填输入框），不进创建请求体。
      void prompt;
      return chatApi.create(body);
    },
    onSuccess: async (session, variables) => {
      await queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      await navigate({
        to: "/chat/$sessionId",
        params: { sessionId: session.id },
        ...(variables.prompt !== undefined
          ? { search: { prompt: variables.prompt } }
          : {}),
      });
    },
  });
}
