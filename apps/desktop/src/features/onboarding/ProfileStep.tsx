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
} from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { settingsKeys } from "@/features/settings/api/keys";
import { profileApi, type ProfileOut } from "@/features/settings/api/profile";
import { StepHeader } from "@/features/onboarding/StepHeader";
import { ROLE_KEYS, isRoleKey, type RoleKey } from "@/features/settings/roles";

const ABOUT_ME_MAX = 200;

type Props = {
  current: number;
  onNext: () => void;
};

/** 向导③角色：跳过=不建档（chat 走中性默认）；已有档案（如导入恢复）时回填并提示。 */
export function ProfileStep({ current, onNext }: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const profile = useQuery({
    queryKey: settingsKeys.profile,
    queryFn: profileApi.get,
  });

  if (profile.isPending) {
    return (
      <div>
        <StepHeader
          current={current}
          title={t("onboarding.profile.title")}
          description={t("onboarding.profile.description")}
        />
        <p
          role="status"
          className="text-body text-muted-foreground mt-10 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("settings.profile.loading")}
        </p>
      </div>
    );
  }
  if (profile.isError) {
    return (
      <div>
        <StepHeader
          current={current}
          title={t("onboarding.profile.title")}
          description={t("onboarding.profile.description")}
        />
        <Alert variant="destructive" className="mt-10 w-auto">
          <AlertDescription>{profile.error.message}</AlertDescription>
        </Alert>
        <Button
          variant="outline"
          className="mt-6"
          onClick={() => void profile.refetch()}
        >
          {t("settings.profile.retry")}
        </Button>
      </div>
    );
  }

  return (
    <div>
      <StepHeader
        current={current}
        title={t("onboarding.profile.title")}
        description={t("onboarding.profile.description")}
      />
      {/* key 随服务端档案变化：导入恢复的已有档案到达后以服务端事实重挂回填。 */}
      <ProfileForm
        key={`${profile.data.nickname ?? ""}|${profile.data.primary_role ?? "none"}|${profile.data.about_me ?? ""}`}
        initial={profile.data}
        existing={profile.data.primary_role !== null}
        onNext={onNext}
        invalidate={() =>
          queryClient.invalidateQueries({ queryKey: settingsKeys.profile })
        }
      />
    </div>
  );
}

function ProfileForm({
  initial,
  existing,
  onNext,
  invalidate,
}: {
  initial: ProfileOut;
  existing: boolean;
  onNext: () => void;
  invalidate: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [role, setRole] = useState<RoleKey | null>(
    initial.primary_role ?? null,
  );
  const [aboutMe, setAboutMe] = useState(initial.about_me ?? "");

  const save = useMutation({
    mutationFn: (payload: {
      primary_role: RoleKey;
      nickname: string | null;
      about_me: string | null;
    }) => profileApi.save(payload),
    onSuccess: async () => {
      await invalidate();
      onNext();
    },
  });

  return (
    <div className="mt-10 flex flex-col gap-6">
      {existing ? (
        <p role="status" className="text-body text-muted-foreground">
          {t("onboarding.profile.existing")}
        </p>
      ) : null}
      <Field>
        <FieldLegend variant="label">
          {t("settings.profile.roleLegend")}
        </FieldLegend>
        <RadioGroup
          value={role ?? ""}
          onValueChange={(value) => {
            if (isRoleKey(value)) setRole(value);
          }}
          disabled={save.isPending}
        >
          {ROLE_KEYS.map((key) => {
            const id = `onboarding-role-${key}`;
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
        <FieldLabel htmlFor="onboarding-about-me">
          {t("settings.profile.aboutMeLabel")}
        </FieldLabel>
        <Textarea
          id="onboarding-about-me"
          value={aboutMe}
          rows={4}
          maxLength={ABOUT_ME_MAX}
          placeholder={t("settings.profile.aboutMePlaceholder")}
          disabled={save.isPending}
          onChange={(event) => setAboutMe(event.target.value)}
        />
        <FieldDescription className="text-end">
          {t("settings.profile.charCount", { count: aboutMe.length })}
        </FieldDescription>
      </Field>
      {save.isError ? (
        <Alert variant="destructive" className="w-auto">
          <AlertDescription>{save.error.message}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex gap-2">
        <Button
          disabled={role === null || save.isPending}
          onClick={() =>
            role !== null &&
            // nickname 不在向导收集：保留服务端已有值，避免保存时静默清空。
            save.mutate({
              primary_role: role,
              nickname: initial.nickname ?? null,
              about_me: aboutMe.trim() || null,
            })
          }
        >
          {save.isPending ? (
            <Spinner
              data-icon="inline-start"
              aria-label={t("onboarding.profile.saving")}
            />
          ) : null}
          {t("onboarding.profile.save")}
        </Button>
        <Button variant="outline" disabled={save.isPending} onClick={onNext}>
          {t("onboarding.profile.skip")}
        </Button>
      </div>
    </div>
  );
}
