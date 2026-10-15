import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { learningPlanKeys } from "@/features/learningPlan/api/keys";
import { todayKeys } from "@/features/today/api/keys";

export function useTodayRefresh() {
  const [now, setNow] = useState(() => new Date());
  const queryClient = useQueryClient();
  const navigate = useNavigate({ from: "/" });
  useEffect(() => {
    let day = new Date().toDateString();
    const refresh = (foreground: boolean) => {
      if (document.visibilityState === "hidden") return;
      const current = new Date();
      const changed = day !== current.toDateString();
      day = current.toDateString();
      setNow(current);
      void queryClient.invalidateQueries({ queryKey: todayKeys.recentAssets });
      if (changed || foreground) {
        void queryClient.invalidateQueries({ queryKey: learningPlanKeys.all });
      }
      if (changed) {
        void navigate({
          search: (previous) => ({ ...previous, completed_page: 1 }),
          replace: true,
        });
      }
    };
    const foreground = () => refresh(true);
    const timer = window.setInterval(() => refresh(false), 60_000);
    document.addEventListener("visibilitychange", foreground);
    window.addEventListener("focus", foreground);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", foreground);
      window.removeEventListener("focus", foreground);
    };
  }, [navigate, queryClient]);
  return now;
}
