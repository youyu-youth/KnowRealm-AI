import { useCallback } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  isRecordCitation,
  isWebCitation,
  type ChatCitation,
} from "@/features/chat/api/types";
import { openWebUrl } from "@/services/tauri/webLinks";

/** 引用点击分流：web 条目经系统浏览器打开外链，record 条目跳转写页并携带定位摘录。 */
export function useOpenCitation() {
  const navigate = useNavigate();
  return useCallback(
    (citation: ChatCitation) => {
      if (isWebCitation(citation)) {
        void openWebUrl(citation.url).catch(() => undefined);
        return;
      }
      if (isRecordCitation(citation)) {
        void navigate({
          to: "/records/$recordId",
          params: { recordId: citation.record_id },
          search: { tab: "transcript", highlight: citation.quote },
        });
      }
    },
    [navigate],
  );
}
