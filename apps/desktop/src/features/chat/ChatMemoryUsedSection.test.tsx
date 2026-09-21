// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { useChatUiStore } from "@/features/chat/chatUiStore";
import { ChatMemoryUsedSection } from "./ChatMemoryUsedSection";

const SESSION_ID = "session-1";

beforeEach(() => {
  useChatUiStore.setState({ turnMemory: null });
});

describe("ChatMemoryUsedSection", () => {
  it("本轮未发送消息（无当轮记忆态）时不渲染", () => {
    const { container } = renderWithQuery(
      <ChatMemoryUsedSection sessionId={SESSION_ID} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("展示本轮注入的记忆条目（边框卡片）", () => {
    useChatUiStore.setState({
      turnMemory: {
        sessionId: SESSION_ID,
        memoryUsed: ["先看例题", "多给反例"],
        proposals: [],
        researchProposals: [],
        operationProposals: [],
      },
    });
    renderWithQuery(<ChatMemoryUsedSection sessionId={SESSION_ID} />);
    expect(
      screen.getByRole("region", { name: "本轮 AI 记忆" }),
    ).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "本轮 AI 记忆" });
    expect(list).toHaveTextContent("先看例题");
    expect(list).toHaveTextContent("多给反例");
  });

  it("本轮零注入（外发关闭/无记忆）展示空态说明", () => {
    useChatUiStore.setState({
      turnMemory: {
        sessionId: SESSION_ID,
        memoryUsed: [],
        proposals: [],
        researchProposals: [],
        operationProposals: [],
      },
    });
    renderWithQuery(<ChatMemoryUsedSection sessionId={SESSION_ID} />);
    expect(screen.getByText("本轮未使用任何记忆。")).toBeInTheDocument();
  });

  it("其他会话的当轮记忆不串显", () => {
    useChatUiStore.setState({
      turnMemory: {
        sessionId: "session-2",
        memoryUsed: ["别的会话的记忆"],
        proposals: [],
        researchProposals: [],
        operationProposals: [],
      },
    });
    const { container } = renderWithQuery(
      <ChatMemoryUsedSection sessionId={SESSION_ID} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
