import { describe, expect, it } from "vitest";
import { parseResumeHref } from "@/features/today/resumeTarget";

const id = "12345678-1234-1234-1234-123456789abc";

describe("续学链接白名单", () => {
  it("识别三类目标与合法 Tab", () => {
    expect(parseResumeHref(`/records/${id}?tab=transcript`)).toMatchObject({
      kind: "RECORD",
      record_tab: "transcript",
    });
    expect(parseResumeHref(`/spaces/${id}/tests/${id}`)).toMatchObject({
      kind: "QUIZ_TEST",
      course_id: id,
    });
    expect(parseResumeHref(`/chat/${id}`)).toMatchObject({
      kind: "CHAT_SESSION",
    });
  });
  it.each([
    `https://example.com/records/${id}`,
    `//example.com/chat/${id}`,
    `/records/${id}?tab=transcript&prompt=send`,
    `/records/${id}?tab=bad`,
    `/records/${id}?tab=quiz?ignored=1`,
    `/records/${id}?tab=quiz&tab=todo`,
    `/chat/${id}?prompt=send`,
    `/settings`,
    `/records/invalid`,
    `/records/${id}#anchor`,
    `javascript:alert(1)`,
  ])("不接管越界链接 %s", (href) => expect(parseResumeHref(href)).toBeNull());
});
