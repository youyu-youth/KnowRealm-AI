import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ClipboardPaste, Mic, NotebookPen, Plus, Upload } from "lucide-react";
import { useTranslation } from "react-i18next";
import { AppTooltip } from "@/components/common/AppTooltip";
import { Button } from "@/components/ui/button";

const actions = [
  { labelKey: "capture.note", icon: NotebookPen },
  { labelKey: "capture.paste", icon: ClipboardPaste },
  { labelKey: "capture.import", icon: Upload },
  { labelKey: "capture.record", icon: Mic },
] as const;

type Props = {
  onCapture: (action: (typeof actions)[number]["labelKey"]) => void;
  recordingActive: boolean;
};

export function CaptureFloatingToolbar({ onCapture, recordingActive }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dragRef = useRef<{
    pointerId: number;
    x: number;
    y: number;
    origin: { x: number; y: number };
  } | null>(null);
  const movedRef = useRef(false);
  const [expanded, setExpanded] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [position, setPosition] = useState(() => ({
    x: 24,
    y: window.innerHeight - 72,
  }));
  const [bounds, setBounds] = useState(() => ({
    left: 0,
    top: 0,
    right: window.innerWidth,
    bottom: window.innerHeight,
    size: 48,
  }));

  const clamp = (next: typeof position) => ({
    x: Math.max(
      bounds.left + 16,
      Math.min(next.x, bounds.right - bounds.size - 16),
    ),
    y: Math.max(
      bounds.top + 16,
      Math.min(next.y, bounds.bottom - bounds.size - 16),
    ),
  });
  const current = clamp(position);
  const opensUp =
    current.y - bounds.top > bounds.bottom - current.y - bounds.size;

  const stopDragging = useCallback((cancel = false) => {
    const drag = dragRef.current;
    dragRef.current = null;
    if (cancel && drag) setPosition(drag.origin);
    if (drag && triggerRef.current?.hasPointerCapture(drag.pointerId)) {
      triggerRef.current.releasePointerCapture(drag.pointerId);
    }
    setDragging(false);
  }, []);

  useEffect(() => {
    const root = rootRef.current;
    const trigger = triggerRef.current;
    const surface = root?.parentElement;
    if (!surface || !root) return;
    const measure = () => {
      const rect = surface.getBoundingClientRect();
      setBounds({
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        size: root.getBoundingClientRect().width,
      });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(surface);
    observer.observe(root);
    const onBlur = () => {
      stopDragging(true);
      setExpanded(false);
    };
    window.addEventListener("resize", measure);
    window.addEventListener("blur", onBlur);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
      window.removeEventListener("blur", onBlur);
      const drag = dragRef.current;
      dragRef.current = null;
      if (drag && trigger?.hasPointerCapture(drag.pointerId)) {
        trigger.releasePointerCapture(drag.pointerId);
      }
    };
  }, [stopDragging]);

  return (
    <div
      ref={rootRef}
      className="capture-floating-toolbar fixed z-30 size-12"
      style={{ left: current.x, top: current.y }}
      onMouseEnter={() => {
        if (!dragRef.current) setExpanded(true);
      }}
      onMouseLeave={(event) => {
        if (!event.currentTarget.contains(document.activeElement))
          setExpanded(false);
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget))
          setExpanded(false);
      }}
      onKeyDownCapture={(event) => {
        if (event.key !== "Escape") return;
        event.preventDefault();
        event.stopPropagation();
        stopDragging(true);
        setExpanded(false);
        triggerRef.current?.focus();
      }}
    >
      <AppTooltip label={t("capture.floatingHint")} side="left">
        <Button
          ref={triggerRef}
          size="icon"
          aria-label={t("capture.label")}
          aria-expanded={expanded}
          aria-controls={id}
          className="capture-fab size-12 touch-none rounded-full shadow-lg focus-visible:ring-3"
          data-dragging={dragging || undefined}
          onClick={(event) => {
            if (!movedRef.current || event.detail === 0)
              setExpanded((value) => !value);
          }}
          onKeyDown={(event) => {
            const direction = {
              ArrowLeft: [-16, 0],
              ArrowRight: [16, 0],
              ArrowUp: [0, -16],
              ArrowDown: [0, 16],
            }[event.key];
            if (!direction) return;
            event.preventDefault();
            setPosition(
              clamp({
                x: current.x + direction[0],
                y: current.y + direction[1],
              }),
            );
          }}
          onPointerDown={(event) => {
            if (event.button !== 0 || event.isPrimary === false) return;
            event.preventDefault();
            movedRef.current = false;
            dragRef.current = {
              pointerId: event.pointerId,
              x: event.clientX,
              y: event.clientY,
              origin: current,
            };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            const drag = dragRef.current;
            if (!drag || drag.pointerId !== event.pointerId) return;
            const dx = event.clientX - drag.x;
            const dy = event.clientY - drag.y;
            if (!movedRef.current && Math.hypot(dx, dy) < 4) return;
            movedRef.current = true;
            setDragging(true);
            setExpanded(false);
            setPosition(
              clamp({ x: drag.origin.x + dx, y: drag.origin.y + dy }),
            );
          }}
          onPointerUp={() => stopDragging()}
          onPointerCancel={() => stopDragging(true)}
          onLostPointerCapture={() => stopDragging()}
        >
          <Plus aria-hidden="true" />
        </Button>
      </AppTooltip>
      <div
        id={id}
        role="group"
        aria-label={t("capture.label")}
        inert={!expanded}
        className="capture-floating-actions absolute -left-1 flex w-14 flex-col gap-2 overflow-y-auto px-1"
        data-open={expanded || undefined}
        data-side={opensUp ? "top" : "bottom"}
        style={{
          maxHeight: Math.max(
            0,
            opensUp
              ? current.y - bounds.top - 16
              : bounds.bottom - current.y - bounds.size - 16,
          ),
        }}
      >
        {actions.map(({ labelKey, icon: Icon }) => {
          const unavailable = labelKey === "capture.record" && recordingActive;
          return (
            <AppTooltip
              key={labelKey}
              label={unavailable ? t("capture.recordingActive") : t(labelKey)}
              side="left"
            >
              <Button
                variant="secondary"
                size="icon"
                aria-label={t(labelKey)}
                disabled={unavailable}
                focusableWhenDisabled
                className="capture-fab size-12 rounded-full shadow-sm focus-visible:ring-3 disabled:pointer-events-auto"
                onClick={() => {
                  if (unavailable) return;
                  setExpanded(false);
                  triggerRef.current?.focus();
                  onCapture(labelKey);
                }}
              >
                <Icon aria-hidden="true" />
              </Button>
            </AppTooltip>
          );
        })}
      </div>
    </div>
  );
}
