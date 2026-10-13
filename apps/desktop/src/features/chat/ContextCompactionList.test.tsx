// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import { fireEvent, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import i18n from "@/i18n";
import { ContextCompactionList } from "@/features/chat/ContextCompactionList";

afterEach(async () => {
  await i18n.changeLanguage("zh");
});

it("展开六栏摘要，显示来源与真实请求进度", async () => {
  const batch: components["schemas"]["CompactionOut"] = {
    id: "batch",
    status: "COMPLETED",
    completed_chunks: 2,
    total_chunks: 2,
    requests_used: 3,
    turn_requests_used: 3,
    allowance: 4,
    covered_message_ids: ["original-user"],
    error_code: null,
    summary: {
      goals: [{ text: "复习图论", source_ids: ["original-user"] }],
      constraints: [],
      decisions: [],
      objects: [],
      unfinished: [],
      questions: [],
    },
  };
  renderWithQuery(<ContextCompactionList batches={[batch]} showSummary />);
  expect(screen.getByRole("status")).toHaveTextContent("所属轮次摘要请求 3/4");
  fireEvent.click(screen.getByRole("button", { name: "查看六栏摘要与来源" }));
  expect(await screen.findByText("复习图论")).toBeVisible();
  expect(screen.getByText(/original-user/)).toBeVisible();
  expect(screen.getAllByRole("heading")).toHaveLength(6);
  expect(screen.getByText(/不保证语义无损/)).toBeVisible();
});

it.each(["zh", "en"])("%s 区分单批请求与所属轮次累计额度", async (language) => {
  await i18n.changeLanguage(language);
  const batches: components["schemas"]["CompactionOut"][] = [
    {
      id: "completed",
      status: "COMPLETED",
      completed_chunks: 2,
      total_chunks: 2,
      requests_used: 2,
      turn_requests_used: 4,
      allowance: 4,
      covered_message_ids: [],
      summary: null,
      error_code: null,
    },
    {
      id: "waiting",
      status: "WAITING",
      completed_chunks: 1,
      total_chunks: 2,
      requests_used: 2,
      turn_requests_used: 4,
      allowance: 4,
      covered_message_ids: [],
      summary: null,
      error_code: null,
    },
  ];
  renderWithQuery(<ContextCompactionList batches={batches} />);
  for (const status of screen.getAllByRole("status")) {
    expect(status).toHaveTextContent(
      language === "zh" ? "本批请求 2" : "Batch requests 2",
    );
    expect(status).toHaveTextContent(
      language === "zh" ? "所属轮次摘要请求 4/4" : "Turn summary requests 4/4",
    );
  }
});
