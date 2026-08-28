import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { settingsKeys } from "@/features/settings/api/keys";
import { profileApi } from "@/features/settings/api/profile";
import type { ProfileOut } from "@/features/settings/api/profile";

const ROLE_KEYS = ["STUDENT", "DEVELOPER", "OFFICE_WORKER", "OTHER"] as const;
type RoleKey = (typeof ROLE_KEYS)[number];

const ABOUT_ME_MAX = 200;

function isRoleKey(value: string): value is RoleKey {
  return (ROLE_KEYS as readonly string[]).includes(value);
}

export function SettingsPage() {
  const { t } = useTranslation();
  const profile = useQuery({
    queryKey: settingsKeys.profile,
    queryFn: () => profileApi.get(),
  });

  if (profile.isPending) {
    return (
      <section className="max-w-workbench px-content mx-auto py-8">
        <h1 className="text-headline font-headline text-ink-strong">
          {t("settings.title")}
        </h1>
        <p
          role="status"
          className="text-body text-muted-foreground mt-6 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("settings.profile.loading")}
        </p>
      </section>
    );
  }

  if (profile.isError) {
    return (
      <section role="alert" className="max-w-workbench px-content mx-auto py-8">
        <h1 className="text-headline font-headline text-ink-strong">
          {t("settings.title")}
        </h1>
        <h2 className="text-section font-section text-ink mt-6">
          {t("settings.profile.errorTitle")}
        </h2>
        <p className="max-w-reading text-body text-muted-foreground mt-2">
          {profile.error.message}
        </p>
        <Button
          variant="outline"
          className="mt-5"
          onClick={() => void profile.refetch()}
        >
          {t("settings.profile.retry")}
        </Button>
      </section>
    );
  }

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto min-w-0 py-8">
      <h1 className="text-headline font-headline text-ink-strong">
        {t("settings.title")}
      </h1>
      <div className="border-border max-w-reading mt-8 border-t pt-8">
        <h2 className="text-section font-section text-ink">
          {t("settings.profile.sectionTitle")}
        </h2>
        <p className="max-w-reading text-body text-muted-foreground">
          {t("settings.profile.sectionDescription")}
        </p>
        {/* key 随服务端档案内容变化：保存成功并重取后表单以最新档案重挂载，回显服务端事实。 */}
        <ProfileForm
          key={`${profile.data.primary_role ?? "none"}|${profile.data.about_me ?? ""}`}
          initial={profile.data}
        />
      </div>
    </section>
  );
}

function ProfileForm({ initial }: { initial: ProfileOut }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [role, setRole] = useState<RoleKey | null>(
    initial.primary_role ?? null,
  );
  const [aboutMe, setAboutMe] = useState(initial.about_me ?? "");

  const saveProfile = useMutation({
    mutationFn: (payload: { primary_role: RoleKey; about_me: string | null }) =>
      profileApi.save(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: settingsKeys.profile });
    },
  });

  return (
    <FieldSet className="mt-6 gap-5">
      <Field>
        <FieldLegend variant="label">
          {t("settings.profile.roleLegend")}
        </FieldLegend>
        <RadioGroup
          value={role ?? ""}
          onValueChange={(value) => {
            if (isRoleKey(value)) setRole(value);
          }}
          disabled={saveProfile.isPending}
        >
          {ROLE_KEYS.map((key) => {
            const id = `profile-role-${key}`;
            return (
              <Field key={id} orientation="horizontal">
                <RadioGroupItem id={id} value={key} />
                <FieldLabel htmlFor={id}>
                  {t(`settings.profile.role.${key}`)}
                </FieldLabel>
              </Field>
            );
          })}
        </RadioGroup>
      </Field>

      <Field>
        <FieldLabel htmlFor="profile-about-me">
          {t("settings.profile.aboutMeLabel")}
        </FieldLabel>
        <Textarea
          id="profile-about-me"
          value={aboutMe}
          rows={4}
          maxLength={ABOUT_ME_MAX}
          placeholder={t("settings.profile.aboutMePlaceholder")}
          disabled={saveProfile.isPending}
          onChange={(event) => setAboutMe(event.target.value)}
        />
        <FieldDescription className="text-end">
          {t("settings.profile.charCount", { count: aboutMe.length })}
        </FieldDescription>
      </Field>

      {saveProfile.isError ? (
        <Alert variant="destructive" className="w-auto">
          <AlertDescription>{saveProfile.error.message}</AlertDescription>
        </Alert>
      ) : null}
      {saveProfile.isSuccess ? (
        <p role="status" className="text-body text-muted-foreground">
          {t("settings.profile.savedFeedback")}
        </p>
      ) : null}

      <div>
        <Button
          disabled={role === null || saveProfile.isPending}
          onClick={() =>
            role !== null &&
            saveProfile.mutate({
              primary_role: role,
              about_me: aboutMe.trim() || null,
            })
          }
        >
          {saveProfile.isPending ? (
            <Spinner
              data-icon="inline-start"
              aria-label={t("settings.profile.saving")}
            />
          ) : null}
          {t("settings.profile.save")}
        </Button>
      </div>
    </FieldSet>
  );
}
