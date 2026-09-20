import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Bot,
  Database,
  MonitorCog,
  Palette,
  SlidersHorizontal,
  UserRound,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AvatarImage } from "@/components/common/AvatarImage";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { settingsKeys } from "@/features/settings/api/keys";
import { useProfileAvatar } from "@/features/settings/api/queries";
import { profileApi } from "@/features/settings/api/profile";
import type { ProfileOut } from "@/features/settings/api/profile";
import {
  SettingsActions,
  SettingsChoiceRow,
  SettingsPanelHeader,
  SettingsRow,
} from "@/features/settings/SettingsLayout";
import { PreferencesSection } from "@/features/settings/PreferencesSection";
import { ProvidersSection } from "@/features/settings/ProvidersSection";
import { LearnerMemorySection } from "@/features/settings/LearnerMemorySection";
import { DataDirectorySection } from "@/features/settings/DataDirectorySection";
import { ROLE_KEYS, isRoleKey, type RoleKey } from "@/features/settings/roles";
import {
  isSettingsSection,
  type SettingsSection,
} from "@/features/settings/sections";

const ABOUT_ME_MAX = 200;
const NICKNAME_MAX = 20;

const SETTINGS_NAV_GROUPS = [
  {
    labelKey: "settings.navigation.account",
    items: [
      {
        value: "profile",
        labelKey: "settings.navigation.profile",
        icon: UserRound,
      },
    ],
  },
  {
    labelKey: "settings.navigation.services",
    items: [
      {
        value: "ai",
        labelKey: "settings.navigation.ai",
        icon: Bot,
      },
    ],
  },
  {
    labelKey: "settings.navigation.application",
    items: [
      {
        value: "appearance",
        labelKey: "settings.navigation.appearance",
        icon: Palette,
      },
      {
        value: "desktop",
        labelKey: "settings.navigation.desktop",
        icon: MonitorCog,
      },
      {
        value: "general",
        labelKey: "settings.navigation.general",
        icon: SlidersHorizontal,
      },
    ],
  },
  {
    labelKey: "settings.navigation.dataGroup",
    items: [
      {
        value: "data",
        labelKey: "settings.navigation.data",
        icon: Database,
      },
    ],
  },
] as const;

type SettingsPageProps = {
  section: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
};

export function SettingsPage({ section, onSectionChange }: SettingsPageProps) {
  const { t } = useTranslation();

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto min-w-0 py-8">
      <header>
        <h1 className="text-headline font-headline text-ink-strong">
          {t("settings.title")}
        </h1>
      </header>

      <Tabs
        value={section}
        orientation="vertical"
        onValueChange={(value) => {
          if (isSettingsSection(value)) onSectionChange(value);
        }}
        className="mt-8 grid min-w-0 gap-8 md:grid-cols-[12rem_minmax(0,1fr)] md:gap-4"
      >
        <TabsList
          variant="line"
          activateOnFocus
          aria-label={t("settings.navigation.label")}
          className="bg-canvas sticky top-0 z-10 flex w-full [scrollbar-width:none] items-stretch gap-1 self-start overflow-x-auto py-2 max-md:group-data-vertical/tabs:flex-row md:w-auto md:flex-col md:overflow-visible md:py-0 [&::-webkit-scrollbar]:hidden"
        >
          {SETTINGS_NAV_GROUPS.map((group) => (
            <div
              key={group.labelKey}
              className="flex shrink-0 flex-col gap-1 max-md:flex-row md:w-full"
            >
              <p className="text-label font-label text-muted-foreground px-3 pt-4 first:pt-0 max-md:hidden">
                {t(group.labelKey)}
              </p>
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <TabsTrigger
                    key={item.value}
                    value={item.value}
                    className="hover:bg-surface-subtle data-active:!bg-surface-subtle h-10 justify-start rounded-md px-3 after:hidden data-active:shadow-none"
                  >
                    <Icon aria-hidden="true" />
                    {t(item.labelKey)}
                  </TabsTrigger>
                );
              })}
            </div>
          ))}
        </TabsList>

        <div className="md:border-border/60 min-w-0 md:border-l md:pl-4">
          <TabsContent value="profile" keepMounted className="min-w-0">
            <ProfileSection />
            <LearnerMemorySection />
          </TabsContent>
          <TabsContent value="ai" keepMounted className="min-w-0">
            <ProvidersSection />
          </TabsContent>
          <PreferencesSection />
          <TabsContent value="data" keepMounted className="min-w-0">
            <DataDirectorySection />
          </TabsContent>
        </div>
      </Tabs>
    </section>
  );
}

function ProfileSection() {
  const { t } = useTranslation();
  const profile = useQuery({
    queryKey: settingsKeys.profile,
    queryFn: () => profileApi.get(),
  });

  if (profile.isPending) {
    return (
      <section aria-labelledby="settings-profile-title">
        <SettingsPanelHeader
          id="settings-profile-title"
          title={t("settings.navigation.profile")}
        />
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
      <section role="alert" aria-labelledby="settings-profile-error-title">
        <h2
          id="settings-profile-error-title"
          className="text-headline font-headline text-ink-strong"
        >
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
    <section aria-labelledby="settings-profile-title" className="max-w-5xl">
      <SettingsPanelHeader
        id="settings-profile-title"
        title={t("settings.navigation.profile")}
      />
      {/* key 随服务端档案内容变化：保存成功并重取后表单以最新档案重挂载，回显服务端事实。 */}
      <ProfileForm
        key={`${profile.data.nickname ?? ""}|${profile.data.primary_role ?? "none"}|${profile.data.about_me ?? ""}`}
        initial={profile.data}
      />
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
    <div className="mt-8 flex flex-col gap-8">
      <SettingsRow
        label={t("settings.profile.nicknameLabel")}
        htmlFor="profile-nickname"
      >
        <Input
          id="profile-nickname"
          value={nickname}
          maxLength={NICKNAME_MAX}
          placeholder={t("settings.profile.nicknamePlaceholder")}
          disabled={saveProfile.isPending}
          onChange={(event) => setNickname(event.target.value)}
        />
      </SettingsRow>

      <AvatarField />

      <SettingsChoiceRow label={t("settings.profile.roleLegend")}>
        <RadioGroup
          className="flex flex-wrap gap-x-5 gap-y-3"
          value={role ?? ""}
          onValueChange={(value) => {
            if (isRoleKey(value)) setRole(value);
          }}
          disabled={saveProfile.isPending}
        >
          {ROLE_KEYS.map((key) => {
            const id = `profile-role-${key}`;
            return (
              <Field key={id} orientation="horizontal" className="w-auto">
                <RadioGroupItem id={id} value={key} />
                <FieldLabel htmlFor={id}>
                  {t(`settings.profile.role.${key}`)}
                </FieldLabel>
              </Field>
            );
          })}
        </RadioGroup>
      </SettingsChoiceRow>

      <SettingsRow
        label={t("settings.profile.aboutMeLabel")}
        htmlFor="profile-about-me"
      >
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
      </SettingsRow>

      <SettingsActions>
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
        <Button
          className="mt-3"
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
      </SettingsActions>
    </div>
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
    <SettingsRow
      label={t("settings.profile.avatarLabel")}
      description={t("settings.profile.avatarHint")}
    >
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
          <div className="flex flex-wrap gap-2">
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
        </div>
      </div>
      {avatarError ? (
        <Alert variant="destructive" className="w-auto">
          <AlertDescription>{avatarError.message}</AlertDescription>
        </Alert>
      ) : null}
    </SettingsRow>
  );
}
