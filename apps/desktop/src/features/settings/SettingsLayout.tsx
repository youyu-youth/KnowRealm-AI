import type { ReactNode } from "react";
import {
  Field,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";

type SettingsPanelHeaderProps = {
  id: string;
  title: string;
};

export function SettingsPanelHeader({ id, title }: SettingsPanelHeaderProps) {
  return (
    <header>
      <h2 id={id} className="text-headline font-headline text-ink-strong">
        {title}
      </h2>
    </header>
  );
}

type SettingsRowProps = {
  label: string;
  description?: string;
  htmlFor?: string;
  children: ReactNode;
};

export function SettingsRow({
  label,
  description,
  htmlFor,
  children,
}: SettingsRowProps) {
  return (
    <Field className="grid min-w-0 gap-3 sm:grid-cols-[minmax(10rem,0.75fr)_minmax(0,1.25fr)] sm:gap-8">
      <div className="min-w-0">
        {htmlFor ? (
          <FieldLabel htmlFor={htmlFor}>{label}</FieldLabel>
        ) : (
          <p className="text-label font-label text-ink">{label}</p>
        )}
        {description ? (
          <p className="text-label text-muted-foreground mt-1">{description}</p>
        ) : null}
      </div>
      <div className="min-w-0">{children}</div>
    </Field>
  );
}

type SettingsChoiceRowProps = {
  label: string;
  description?: string;
  children: ReactNode;
};

export function SettingsChoiceRow({
  label,
  description,
  children,
}: SettingsChoiceRowProps) {
  return (
    <div className="grid min-w-0 gap-3 sm:grid-cols-[minmax(10rem,0.75fr)_minmax(0,1.25fr)] sm:gap-x-8 sm:gap-y-1">
      <FieldSet className="contents">
        <FieldLegend variant="label" className="col-start-1 row-start-1 mb-0">
          {label}
        </FieldLegend>
        {description ? (
          <p className="text-label text-muted-foreground col-start-1 row-start-2">
            {description}
          </p>
        ) : null}
        <div className="min-w-0 sm:col-start-2 sm:row-span-2 sm:row-start-1">
          {children}
        </div>
      </FieldSet>
    </div>
  );
}

export function SettingsActions({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-w-0 gap-3 sm:grid-cols-[minmax(10rem,0.75fr)_minmax(0,1.25fr)] sm:gap-8">
      <div aria-hidden="true" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
