import { Link, useLocation } from "@tanstack/react-router";
import { MoreHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  activeNavClass,
  inactiveNavClass,
  navigationItems,
} from "@/components/layout/navigationItems";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export function MainNavigation() {
  const { t, i18n } = useTranslation();
  const pathname = useLocation({ select: (location) => location.pathname });
  const containerRef = useRef<HTMLElement>(null);
  const measurementRef = useRef<HTMLDivElement>(null);
  const [visibleCount, setVisibleCount] = useState<number>(
    navigationItems.length,
  );

  useEffect(() => {
    const container = containerRef.current;
    const measurement = measurementRef.current;
    if (!container || !measurement) return;
    const update = () => {
      const available = container.getBoundingClientRect().width;
      if (!available) return;
      const widths = Array.from(
        measurement.children,
        (element) => element.getBoundingClientRect().width,
      );
      const moreWidth = widths.pop() ?? 0;
      const gap =
        Number.parseFloat(getComputedStyle(measurement).columnGap) || 0;
      if (
        widths.reduce((sum, width) => sum + width, 0) +
          gap * (widths.length - 1) <=
        available
      ) {
        setVisibleCount(navigationItems.length);
        return;
      }
      let used = moreWidth;
      let count = 0;
      for (const width of widths) {
        if (used + gap + width > available) break;
        used += gap + width;
        count++;
      }
      setVisibleCount(count);
    };
    const observer = new ResizeObserver(update);
    observer.observe(container);
    observer.observe(measurement);
    update();
    return () => observer.disconnect();
  }, [i18n.resolvedLanguage]);

  const overflow = navigationItems.slice(visibleCount);
  const overflowActive = overflow.some(
    (item) =>
      "to" in item &&
      (pathname === item.to ||
        (item.to !== "/" && pathname.startsWith(`${item.to}/`))),
  );

  return (
    <nav
      ref={containerRef}
      aria-label={t("nav.label")}
      className="relative flex min-w-9 flex-1 items-center gap-1 overflow-hidden"
    >
      {/* 独立测量完整文字，避免隐藏菜单后宽度变化造成反复收放。 */}
      <div
        ref={measurementRef}
        aria-hidden="true"
        inert
        className="pointer-events-none invisible absolute top-0 left-0 flex w-max gap-1"
      >
        {navigationItems.map(({ labelKey, icon: Icon }) => (
          <span
            key={labelKey}
            className={cn(activeNavClass, "shrink-0 whitespace-nowrap")}
          >
            <Icon className="size-4 shrink-0" />
            {t(labelKey)}
          </span>
        ))}
        <span className="size-9 shrink-0" />
      </div>
      {navigationItems.slice(0, visibleCount).map((item) => {
        const Icon = item.icon;
        const label = t(item.labelKey);
        return (
          <Link
            key={item.labelKey}
            to={item.to}
            activeOptions={{ exact: item.to === "/" }}
            activeProps={{ className: activeNavClass }}
            inactiveProps={{ className: inactiveNavClass }}
            className="shrink-0 whitespace-nowrap"
            aria-label={label}
          >
            <Icon className="size-4 shrink-0" aria-hidden="true" />
            {label}
          </Link>
        );
      })}
      {overflow.length > 0 && (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={<Button variant="ghost" size="icon-lg" />}
            aria-label={t("nav.moreNavigation")}
            title={t("nav.moreNavigation")}
            className={cn(
              "shrink-0",
              overflowActive && "bg-surface-subtle text-ink-strong",
            )}
          >
            <MoreHorizontal aria-hidden="true" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuGroup>
              {overflow.map((item) => {
                const Icon = item.icon;
                const label = t(item.labelKey);
                return (
                  <DropdownMenuItem
                    key={item.labelKey}
                    disabled={!("to" in item)}
                    render={
                      "to" in item ? (
                        <Link
                          to={item.to}
                          activeOptions={{ exact: item.to === "/" }}
                          activeProps={{
                            "aria-current": "page",
                            className: "bg-surface-subtle text-ink-strong",
                          }}
                        />
                      ) : undefined
                    }
                  >
                    <Icon aria-hidden="true" />
                    {label}
                    {!("to" in item) && (
                      <span className="text-muted-foreground ml-auto">
                        {t("nav.unavailable")}
                      </span>
                    )}
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </nav>
  );
}
