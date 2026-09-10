import { useEffect, useMemo, useState } from "react";

import { cn } from "@/lib/utils";

type AvatarImageProps = {
  blob: Blob;
  alt: string;
  className?: string;
};

/**
 * 头像 blob → object URL 展示；blob 换代即派生新 URL，
 * 旧 URL 随 effect 清理回收，消费方无需管理生命周期。
 */
export function AvatarImage({ blob, alt, className }: AvatarImageProps) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const url = useMemo(() => URL.createObjectURL(blob), [blob]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);

  if (failedUrl === url) {
    return (
      <span
        role="img"
        aria-label={alt}
        className={cn(
          "bg-surface-strong text-label text-ink-muted inline-flex items-center justify-center font-medium",
          className,
        )}
      >
        {alt.trim().slice(0, 1).toUpperCase()}
      </span>
    );
  }

  return (
    <img
      src={url}
      alt={alt}
      className={className}
      onError={() => setFailedUrl(url)}
    />
  );
}
