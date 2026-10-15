import { useEffect, useRef } from "react";
import {
  useLearningResumeActions,
  type LearningVisit,
} from "@/features/today/api/resume";

export function useLearningVisit(visit: LearningVisit, enabled: boolean) {
  const { mutate } = useLearningResumeActions();
  const recorded = useRef<string | null>(null);
  const { kind, target_id: targetId, record_tab: tab } = visit;
  useEffect(() => {
    if (!enabled) return;
    const key = `${kind}:${targetId}:${tab ?? ""}`;
    const record = () => {
      if (document.visibilityState === "hidden" || recorded.current === key)
        return;
      recorded.current = key;
      mutate(
        {
          action: "visit",
          visit: { kind, target_id: targetId, record_tab: tab },
        },
        {
          onError: () =>
            console.warn("learning_visit_save_failed", { kind, targetId }),
        },
      );
    };
    record();
    document.addEventListener("visibilitychange", record);
    return () => document.removeEventListener("visibilitychange", record);
  }, [enabled, kind, targetId, tab, mutate]);
}
