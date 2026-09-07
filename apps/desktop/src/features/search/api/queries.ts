import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { searchKeys } from "@/features/search/api/keys";
import { searchApi } from "@/features/search/api/search";

const DEBOUNCE_MS = 250;

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

// 可复用搜索 hook（命令面板与资产库视图共用）：输入去抖 250ms 后调 /api/search；
// 空查询不请求。结果分组与排序以后端 FTS5 BM25 为准，前端不再排序。
export function useSearchResults(query: string, limit?: number) {
  const debounced = useDebouncedValue(query, DEBOUNCE_MS);
  return useQuery({
    queryKey: searchKeys.results(debounced, limit),
    queryFn: () => searchApi.search(debounced, limit),
    enabled: debounced.length > 0,
  });
}
