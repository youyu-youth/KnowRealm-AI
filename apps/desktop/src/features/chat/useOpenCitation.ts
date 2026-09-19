import { useCallback } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  isLibraryCitation,
  isRecordCitation,
  isWebCitation,
  type ChatCitation,
} from "@/features/chat/api/types";
import { openWebUrl } from "@/services/tauri/webLinks";

/** 引用点击分流：web 经系统浏览器外链；record 跳转写页定位转写；library 跳转资料库来源预览。 */
export function useOpenCitation() {
  const navigate = useNavigate();
  return useCallback(
    (citation: ChatCitation) => {
      if (isWebCitation(citation)) {
        void openWebUrl(citation.url).catch(() => undefined);
        return;
      }
      if (isLibraryCitation(citation)) {
        void navigate({
          to: "/library",
          search: { sel: citation.library_item_id, selType: "item" },
        });
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
