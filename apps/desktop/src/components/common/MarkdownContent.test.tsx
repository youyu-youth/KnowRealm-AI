// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MarkdownContent } from "@/components/common/MarkdownContent";

vi.mock("shiki", () => ({
  codeToTokensWithThemes: vi.fn().mockResolvedValue([
    [
      {
        content: "const",
        variants: {
          light: { color: "#111111" },
          dark: { color: "#eeeeee" },
        },
      },
    ],
  ]),
}));

describe("MarkdownContent", () => {
  it("安全渲染带语言标记和亮暗主题变量的代码块", async () => {
    const { container } = render(
      <MarkdownContent markdown={"```ts\nconst value = 1\n```"} />,
    );

    const code = (await screen.findByText("const")).closest("code");
    await waitFor(() => expect(code).toHaveAttribute("data-shiki", "true"));
    expect(code).toHaveClass("language-ts");
    const token = container.querySelector<HTMLElement>(".markdown-code-token");
    expect(token?.style.getPropertyValue("--shiki-light")).toBe("#111111");
    expect(token?.style.getPropertyValue("--shiki-dark")).toBe("#eeeeee");
  });
});
