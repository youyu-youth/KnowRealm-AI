import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  APP_SIDEBAR_ID,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  useSidebarUiStore,
} from "@/components/layout/sidebarUiStore";

export function SidebarResizeHandle() {
  const { t } = useTranslation();
  const width = useSidebarUiStore((state) => state.width);
  const setWidth = useSidebarUiStore((state) => state.setWidth);
  const handleRef = useRef<HTMLButtonElement>(null);
  const dragRef = useRef<{
    pointerId: number;
    x: number;
    width: number;
  } | null>(null);
  const [measuredWidth, setMeasuredWidth] = useState(224);

  const stopDragging = () => {
    const pointerId = dragRef.current?.pointerId;
    dragRef.current = null;
    if (
      pointerId !== undefined &&
      handleRef.current?.hasPointerCapture(pointerId)
    ) {
      handleRef.current.releasePointerCapture(pointerId);
    }
    document.documentElement.classList.remove("sidebar-resizing");
  };

  useEffect(() => {
    const sidebar = handleRef.current?.parentElement;
    if (!sidebar) return;
    const observer = new ResizeObserver(() => {
      setMeasuredWidth(sidebar.getBoundingClientRect().width);
    });
    setMeasuredWidth(sidebar.getBoundingClientRect().width);
    observer.observe(sidebar);
    window.addEventListener("blur", stopDragging);
    return () => {
      observer.disconnect();
      window.removeEventListener("blur", stopDragging);
      stopDragging();
    };
  }, []);

  return (
    <Button
      ref={handleRef}
      variant="ghost"
      role="separator"
      aria-label={t("nav.resizeSidebar")}
      aria-orientation="vertical"
      aria-controls={APP_SIDEBAR_ID}
      aria-valuemin={SIDEBAR_MIN_WIDTH}
      aria-valuemax={SIDEBAR_MAX_WIDTH}
      aria-valuenow={width ?? measuredWidth}
      className="sidebar-resize-handle absolute inset-y-0 -right-1 z-10 h-full w-2 touch-none rounded-none border-0 p-0 transition-none active:translate-y-0"
      onPointerDown={(event) => {
        if (event.button !== 0 || event.isPrimary === false) return;
        event.preventDefault();
        event.currentTarget.blur();
        event.currentTarget.setPointerCapture(event.pointerId);
        dragRef.current = {
          pointerId: event.pointerId,
          x: event.clientX,
          width:
            event.currentTarget.parentElement?.getBoundingClientRect().width ??
            measuredWidth,
        };
        document.documentElement.classList.add("sidebar-resizing");
      }}
      onPointerMove={(event) => {
        const drag = dragRef.current;
        if (!drag || event.pointerId !== drag.pointerId) return;
        setWidth(drag.width + event.clientX - drag.x);
      }}
      onPointerUp={stopDragging}
      onPointerCancel={stopDragging}
      onLostPointerCapture={stopDragging}
      onKeyDown={(event) => {
        const currentWidth = width ?? measuredWidth;
        const next = {
          ArrowLeft: currentWidth - 16,
          ArrowRight: currentWidth + 16,
          Home: SIDEBAR_MIN_WIDTH,
          End: SIDEBAR_MAX_WIDTH,
        }[event.key];
        if (event.key === "Escape") stopDragging();
        if (next === undefined) return;
        event.preventDefault();
        setWidth(next);
      }}
    />
  );
}
