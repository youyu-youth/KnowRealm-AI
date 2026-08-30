import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { UserRound } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AvatarImage } from "@/components/common/AvatarImage";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { settingsKeys } from "@/features/settings/api/keys";
import { useProfileAvatar } from "@/features/settings/api/queries";
import { profileApi } from "@/features/settings/api/profile";
import type { ProfileOut } from "@/features/settings/api/profile";
import { PreferencesSection } from "@/features/settings/PreferencesSection";
import { ProvidersSection } from "@/features/settings/ProvidersSection";

const ROLE_KEYS = ["STUDENT", "DEVELOPER", "OFFICE_WORKER", "OTHER"] as const;
type RoleKey = (typeof ROLE_KEYS)[number];

const ABOUT_ME_MAX = 200;
const NICKNAME_MAX = 20;

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
          key={`${profile.data.nickname ?? ""}|${profile.data.primary_role ?? "none"}|${profile.data.about_me ?? ""}`}
          initial={profile.data}
        />
      </div>
      <ProvidersSection />
      <PreferencesSection />
    </section>
  );
}

function ProfileForm({ initial }: { initial: ProfileOut }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [role, setRole] = useState<RoleKey | null>(
    initial.primary_role ?? null,
  );
  const [nickname, setNickname] = useState(initial.nickname ?? "");
  const [aboutMe, setAboutMe] = useState(initial.about_me ?? "");

  const saveProfile = useMutation({
    mutationFn: (payload: {
      primary_role: RoleKey;
      nickname: string | null;
      about_me: string | null;
    }) => profileApi.save(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: settingsKeys.profile });
    },
  });

  return (
    <FieldSet className="mt-6 gap-5">
      <Field>
        <FieldLabel htmlFor="profile-nickname">
          {t("settings.profile.nicknameLabel")}
        </FieldLabel>
        <Input
          id="profile-nickname"
          value={nickname}
          maxLength={NICKNAME_MAX}
          placeholder={t("settings.profile.nicknamePlaceholder")}
          disabled={saveProfile.isPending}
          onChange={(event) => setNickname(event.target.value)}
        />
      </Field>

      <AvatarField />

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
              nickname: nickname.trim() || null,
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

/** 头像即选即传（PUT/DELETE 独立于"保存档案"），取消选择不触发上传。 */
function AvatarField() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const avatar = useProfileAvatar();

  const uploadAvatar = useMutation({
    mutationFn: async (file: File) => {
      await profileApi.putAvatar(new Uint8Array(await file.arrayBuffer()));
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: settingsKeys.profileAvatar,
      });
    },
  });
  const removeAvatar = useMutation({
    mutationFn: () => profileApi.deleteAvatar(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: settingsKeys.profileAvatar,
      });
    },
  });
  const avatarError = uploadAvatar.error ?? removeAvatar.error ?? null;
  const avatarPending = uploadAvatar.isPending || removeAvatar.isPending;

  return (
    <Field>
      <FieldLabel>{t("settings.profile.avatarLabel")}</FieldLabel>
      <div className="flex items-center gap-4">
        <span className="bg-surface-subtle flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-full">
          {avatar.blob ? (
            <AvatarImage
              blob={avatar.blob}
              alt={t("settings.profile.avatarLabel")}
              className="size-full object-cover"
            />
          ) : (
            <UserRound
              className="text-muted-foreground size-8"
              aria-hidden="true"
            />
          )}
        </span>
        <div className="flex flex-col items-start gap-2">
          <div className="flex gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                // 清空 value 允许失败后重选同一文件。
                event.target.value = "";
                if (file) uploadAvatar.mutate(file);
              }}
            />
            <Button
              variant="outline"
              size="sm"
              disabled={avatarPending}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploadAvatar.isPending ? (
                <Spinner
                  data-icon="inline-start"
                  aria-label={t("settings.profile.avatarUploading")}
                />
              ) : null}
              {t("settings.profile.avatarSelect")}
            </Button>
            {avatar.blob ? (
              <Button
                variant="outline"
                size="sm"
                disabled={avatarPending}
                onClick={() => removeAvatar.mutate()}
              >
                {removeAvatar.isPending ? (
                  <Spinner
                    data-icon="inline-start"
                    aria-label={t("settings.profile.avatarRemoving")}
                  />
                ) : null}
                {t("settings.profile.avatarRemove")}
              </Button>
            ) : null}
          </div>
          <FieldDescription>
            {t("settings.profile.avatarHint")}
          </FieldDescription>
        </div>
      </div>
      {avatarError ? (
        <Alert variant="destructive" className="w-auto">
          <AlertDescription>{avatarError.message}</AlertDescription>
        </Alert>
      ) : null}
    </Field>
  );
}
