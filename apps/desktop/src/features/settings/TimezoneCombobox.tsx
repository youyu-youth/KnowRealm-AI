import { ChevronDown } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

// tsconfig lib=ES2020 尚无 supportedValuesOf 的类型声明；WebView2 与 Node 22 运行时均已支持。
const TIMEZONES: readonly string[] = (
  Intl as unknown as { supportedValuesOf: (key: "timeZone") => string[] }
).supportedValuesOf("timeZone");

export function TimezoneCombobox({
  id,
  value,
  onSelect,
  disabled = false,
}: {
  id: string;
  value: string | null;
  onSelect: (timezone: string | null) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      const root = rootRef.current;
      if (root && !root.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  const normalizedQuery = query.trim().toLowerCase();
  const matches = useMemo(
    () =>
      normalizedQuery
        ? TIMEZONES.filter((timezone) =>
            timezone.toLowerCase().includes(normalizedQuery),
          )
        : TIMEZONES,
    [normalizedQuery],
  );

  const select = (timezone: string | null) => {
    onSelect(timezone);
    setOpen(false);
    setQuery("");
  };

  return (
    <div
      ref={rootRef}
      className="relative w-full max-w-xs"
      onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
      }}
    >
      <Button
        id={id}
        type="button"
        variant="outline"
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        className="w-full justify-between font-normal"
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        {value ?? t("settings.preferences.timezone.followSystem")}
        <ChevronDown
          className={cn("size-4 transition-transform", open && "rotate-180")}
        />
      </Button>
      {open ? (
        <div className="bg-popover text-popover-foreground ring-foreground/10 absolute inset-x-0 top-full z-50 mt-1 flex flex-col gap-2 rounded-lg p-2 shadow-md ring-1">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("settings.preferences.timezone.searchPlaceholder")}
            aria-label={t("settings.preferences.timezone.searchLabel")}
            className="h-8"
            autoComplete="off"
          />
          <ul role="listbox" className="max-h-60 overflow-y-auto">
            <TimezoneOption
              label={t("settings.preferences.timezone.followSystem")}
              selected={value === null}
              onSelect={() => select(null)}
            />
            {matches.map((timezone) => (
              <TimezoneOption
                key={timezone}
                label={timezone}
                selected={value === timezone}
                onSelect={() => select(timezone)}
              />
            ))}
          </ul>
          {matches.length === 0 ? (
            <p className="text-label text-muted-foreground px-2 pb-1">
              {t("settings.preferences.timezone.noMatch")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function TimezoneOption({
  label,
  selected,
  onSelect,
}: {
  label: string;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        role="option"
        aria-selected={selected}
        className={cn(
          "hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground flex w-full items-center rounded-md px-2 py-1.5 text-left text-sm outline-hidden",
          selected && "text-ink-strong font-medium",
        )}
        onClick={onSelect}
      >
        {label}
      </button>
    </li>
  );
}
