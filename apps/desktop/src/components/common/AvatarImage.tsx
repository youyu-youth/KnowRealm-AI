import { useEffect, useMemo } from "react";

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
  const url = useMemo(() => URL.createObjectURL(blob), [blob]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  return <img src={url} alt={alt} className={className} />;
}
