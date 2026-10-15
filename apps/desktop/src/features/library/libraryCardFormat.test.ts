import { describe, expect, it } from "vitest";
import type { LibraryItemOut } from "./api/library";
import { libraryCardFormat } from "./libraryCardFormat";

const item: LibraryItemOut = {
  id: "document",
  source_type: "DOCUMENT",
  title: "笔记.pdf",
  course_id: null,
  origin_uri: null,
  local_path: null,
  mime_type: null,
  file_size: null,
  content_hash: "hash",
  fetched_at: null,
  source_metadata: {},
  schema_version: 1,
  favorite: false,
  status: "ACTIVE",
  availability: "RETRIEVABLE",
  created_at: "2026-10-15T00:00:00Z",
  updated_at: "2026-10-15T00:00:00Z",
};

describe("libraryCardFormat", () => {
  it.each([
    ["application/pdf", "pdf"],
    ["text/markdown; charset=utf-8", "markdown"],
    ["text/plain", "txt"],
    ["text/html", "html"],
    [
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "docx",
    ],
  ])("按真实 MIME %s 识别 %s", (mime_type, format) => {
    expect(libraryCardFormat("DOCUMENT", { ...item, mime_type })).toBe(format);
  });

  it("网页抓取产出的 Markdown 仍展示网页；录音保留音频样式", () => {
    expect(
      libraryCardFormat("WEB", { ...item, mime_type: "text/markdown" }),
    ).toBe("html");
    expect(libraryCardFormat("AUDIO", item)).toBe("audio");
  });

  it("兼容原始文件名、路径与通用 MIME，不从可编辑标题猜测格式", () => {
    expect(
      libraryCardFormat("DOCUMENT", {
        ...item,
        mime_type: "text/plain",
        source_metadata: { files: [{ original_name: "README.MD" }] },
      }),
    ).toBe("markdown");
    expect(
      libraryCardFormat("DOCUMENT", {
        ...item,
        local_path: "files/id/report.DOCX",
        source_metadata: { files: [null] },
      }),
    ).toBe("docx");
    expect(libraryCardFormat("DOCUMENT", item)).toBe("document");
    expect(
      libraryCardFormat("DOCUMENT", {
        ...item,
        mime_type: "application/pdf",
        local_path: "note.txt",
      }),
    ).toBe("pdf");
    expect(libraryCardFormat("ASSET")).toBe("asset");
  });
});
