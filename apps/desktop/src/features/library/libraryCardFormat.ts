import type { LibraryItemOut } from "./api/library";

const mimeFormats = {
  "application/pdf": "pdf",
  "text/markdown": "markdown",
  "text/x-markdown": "markdown",
  "text/html": "html",
  "application/xhtml+xml": "html",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
    "docx",
} as const;

const extensionFormats = {
  pdf: "pdf",
  md: "markdown",
  markdown: "markdown",
  txt: "txt",
  html: "html",
  htm: "html",
  docx: "docx",
} as const;

export function libraryCardFormat(
  sourceType: LibraryItemOut["source_type"] | "ASSET",
  item?: LibraryItemOut,
) {
  if (sourceType === "AUDIO") return "audio";
  if (sourceType === "WEB") return "html";
  if (sourceType === "ASSET") return "asset";
  const mime = item?.mime_type?.split(";")[0].trim().toLowerCase();
  if (mime && Object.prototype.hasOwnProperty.call(mimeFormats, mime)) {
    return mimeFormats[mime as keyof typeof mimeFormats];
  }
  const files = item?.source_metadata.files;
  const firstFile: unknown = Array.isArray(files) ? files[0] : undefined;
  const originalName =
    firstFile && typeof firstFile === "object" && "original_name" in firstFile
      ? firstFile.original_name
      : undefined;
  const path =
    typeof originalName === "string" ? originalName : item?.local_path;
  const extension = path?.split(".").pop()?.toLowerCase();
  if (
    extension &&
    Object.prototype.hasOwnProperty.call(extensionFormats, extension)
  ) {
    return extensionFormats[extension as keyof typeof extensionFormats];
  }
  if (mime === "text/plain" || sourceType === "TEXT") return "txt";
  return sourceType === "BOOK" ? "book" : "document";
}
