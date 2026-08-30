import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { UserRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { AvatarImage } from "@/components/common/AvatarImage";
import { settingsKeys } from "@/features/settings/api/keys";
import { useProfileAvatar } from "@/features/settings/api/queries";
import { profileApi } from "@/features/settings/api/profile";

/**
 * 侧边栏底部用户区：头像+昵称快览，点击跳设置页档案区；
 * 不激活导航里的"学习画像"禁用项（那是 17 号功能的入口）。
 */
export function SidebarUserArea() {
  const { t } = useTranslation();
  const profile = useQuery({
    queryKey: settingsKeys.profile,
    queryFn: () => profileApi.get(),
  });
  const avatar = useProfileAvatar();
  const nickname = profile.data?.nickname?.trim() || null;

  return (
    <Link
      to="/settings"
      aria-label={t("nav.userArea.openSettings")}
      className="hover:bg-surface-subtle focus-visible:ring-ring/40 max-compact:justify-center max-compact:px-0 mt-auto flex h-11 items-center gap-3 rounded-md px-3 transition-colors focus-visible:ring-3"
    >
      <span className="bg-surface-subtle flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-full">
        {avatar.blob ? (
          <AvatarImage
            blob={avatar.blob}
            alt={t("nav.userArea.avatarAlt")}
            className="size-full object-cover"
          />
        ) : (
          <UserRound
            className="text-muted-foreground size-5"
            aria-hidden="true"
          />
        )}
      </span>
      <span className="text-body text-muted-foreground max-compact:sr-only min-w-0 truncate">
        {nickname ?? t("nav.userArea.nicknamePlaceholder")}
      </span>
    </Link>
  );
}
