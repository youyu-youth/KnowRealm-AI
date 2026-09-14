import { useQuery } from "@tanstack/react-query";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";

/** 联网搜索可用性：后端已配置搜索供应商 key 才可用；查询失败同样视为不可用（聊天不受影响）。 */
export function useWebSearchAvailability(): boolean {
  const query = useQuery({
    queryKey: settingsKeys.webSearchProvider,
    queryFn: settingsApi.getWebSearchProvider,
  });
  return query.data?.provider?.has_api_key === true;
}
