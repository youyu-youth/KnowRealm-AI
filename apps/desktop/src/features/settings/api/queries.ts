import { useQuery } from "@tanstack/react-query";
import { settingsKeys } from "@/features/settings/api/keys";
import { profileApi } from "@/features/settings/api/profile";

/** 档案头像 blob；展示用 AvatarImage 承接 object URL 生命周期。 */
export function useProfileAvatar(): {
  blob: Blob | null;
  isPending: boolean;
} {
  const avatar = useQuery({
    queryKey: settingsKeys.profileAvatar,
    queryFn: () => profileApi.getAvatar(),
  });
  return { blob: avatar.data ?? null, isPending: avatar.isPending };
}
