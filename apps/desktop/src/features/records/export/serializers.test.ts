import { describe, expect, it } from "vitest";
import {
  buildExportFileName,
  selectActiveQuizzes,
  selectFormalTodos,
  serializeAggregateMarkdown,
  serializeKnowledgePointsMarkdown,
  serializeQuizMarkdown,
  serializeSummaryMarkdown,
  serializeTodoMarkdown,
} from "@/features/records/export/serializers";
import type { QuizOut, TodoOut } from "@/features/records/api/types";

const summaryLabels = {
  assetTitle: "总结",
  topicLabel: "主题",
  abstractLabel: "摘要",
};

const knowledgePointLabels = {
  assetTitle: "知识点",
  importanceLabel: "重要度",
  tagsLabel: "标签",
};

const quizLabels = {
  assetTitle: "习题",
  questionTypeLabel: "题型",
  stemLabel: "题干",
  difficultyLabel: "难度",
  optionsLabel: "选项",
  userAnswerLabel: "用户答案",
  resultLabel: "结果",
  correctAnswerLabel: "正确答案",
  referenceAnswerLabel: "参考答案",
  explanationLabel: "解析",
  pendingSelfAssessment: "待自评",
  questionTypes: {
    MULTIPLE_CHOICE: "选择题",
    MULTIPLE_SELECT: "多选题",
    TRUE_FALSE: "判断题",
    FILL_BLANK: "填空题",
    SHORT_ANSWER: "简答题",
  },
  difficulties: { EASY: "简单", MEDIUM: "中等", HARD: "困难" },
  results: { CORRECT: "正确", WRONG: "错误" },
};

const quiz = (overrides: Partial<QuizOut> & Pick<QuizOut, "id">): QuizOut => {
  const { id, ...rest } = overrides;
  return {
    id,
    record_id: "record-1",
    batch_id: "batch-active",
    generated_from_summary_id: "summary-1",
    generation_status: "ACTIVE",
    question_type: "MULTIPLE_CHOICE",
    stem: "哪个页面置换算法会淘汰最久未使用的页面？",
    options: ["FIFO", "LRU", "Clock"],
    correct_answer: null,
    explanation: null,
    difficulty: "MEDIUM",
    user_answer: null,
    answer_result: null,
    answered_at: null,
    created_at: "2026-08-26T00:00:00Z",
    updated_at: "2026-08-26T00:00:00Z",
    ...rest,
  };
};

const todo = (
  overrides: Partial<TodoOut> & Pick<TodoOut, "id" | "sort_order">,
): TodoOut => {
  const { id, sort_order, ...rest } = overrides;
  return {
    id,
    sort_order,
    record_id: "record-1",
    batch_id: null,
    content: "整理本节笔记",
    status: "TODO",
    source: "MANUAL",
    generated_from_summary_id: null,
    generation_status: null,
    created_at: "2026-08-26T00:00:00Z",
    updated_at: "2026-08-26T00:00:00Z",
    ...rest,
  };
};

const summarySnapshot = {
  topic: "虚拟内存",
  abstract:
    "虚拟内存通过地址空间抽象隔离进程，并借助分页机制按需映射物理内存。",
  sections: [
    {
      heading: "核心机制",
      points: [
        "页表完成虚拟地址到物理地址的转换。",
        "缺页中断按需调入物理页。",
      ],
    },
    { heading: "隔离与共享", points: ["地址空间隔离防止进程互相破坏。"] },
  ],
};

describe("serializeSummaryMarkdown", () => {
  it("以 Record 标题为一级标题、总结为二级标题，按原顺序输出主题、摘要与分点", () => {
    const markdown = serializeSummaryMarkdown(
      "操作系统第一讲",
      summarySnapshot,
      summaryLabels,
    );

    expect(markdown).toBe(
      [
        "# 操作系统第一讲",
        "",
        "## 总结",
        "",
        "**主题**：虚拟内存",
        "",
        "**摘要**：虚拟内存通过地址空间抽象隔离进程，并借助分页机制按需映射物理内存。",
        "",
        "### 核心机制",
        "",
        "- 页表完成虚拟地址到物理地址的转换。",
        "- 缺页中断按需调入物理页。",
        "",
        "### 隔离与共享",
        "",
        "- 地址空间隔离防止进程互相破坏。",
        "",
      ].join("\n"),
    );
  });

  it("相同输入生成完全相同的内容", () => {
    const first = serializeSummaryMarkdown(
      "标题",
      summarySnapshot,
      summaryLabels,
    );
    const second = serializeSummaryMarkdown(
      "标题",
      summarySnapshot,
      summaryLabels,
    );
    expect(first).toBe(second);
  });
});

describe("serializeKnowledgePointsMarkdown", () => {
  it("每项包含名称分节、详情正文、importance/5 与非空标签，顺序与页面一致", () => {
    const markdown = serializeKnowledgePointsMarkdown(
      "操作系统第一讲",
      [
        {
          name: "进程调度",
          detail: "调度器从就绪队列中选择下一个运行的进程。",
          importance: 5,
          tags: ["操作系统", "调度"],
        },
        {
          name: "时间片",
          detail: "时间片轮转防止单一进程垄断处理器。",
          importance: 4,
          tags: [],
        },
      ],
      knowledgePointLabels,
    );

    expect(markdown).toBe(
      [
        "# 操作系统第一讲",
        "",
        "## 知识点",
        "",
        "### 进程调度",
        "",
        "调度器从就绪队列中选择下一个运行的进程。",
        "",
        "- 重要度：5/5",
        "- 标签：操作系统、调度",
        "",
        "### 时间片",
        "",
        "时间片轮转防止单一进程垄断处理器。",
        "",
        "- 重要度：4/5",
        "",
      ].join("\n"),
    );
  });

  it("多个标签按原顺序拼接，空标签不产生标签行", () => {
    const markdown = serializeKnowledgePointsMarkdown(
      "标题",
      [
        {
          name: "仅一个标签",
          detail: "详情",
          importance: 1,
          tags: ["唯一"],
        },
      ],
      knowledgePointLabels,
    );
    expect(markdown).toContain("- 标签：唯一");
    expect(markdown).not.toContain("- 标签：\n");
  });
});

describe("serializeQuizMarkdown", () => {
  it("未作答 ACTIVE 题只输出题型、题干、难度与页面顺序选项", () => {
    const markdown = serializeQuizMarkdown(
      "操作系统第一讲",
      selectActiveQuizzes([
        quiz({ id: "draft", generation_status: "DRAFT" }),
        quiz({ id: "active", correct_answer: null, explanation: null }),
        quiz({ id: "old", generation_status: "SUPERSEDED" }),
      ]),
      quizLabels,
    );

    expect(markdown).toBe(
      [
        "# 操作系统第一讲",
        "",
        "## 习题",
        "",
        "### 1",
        "",
        "- 题型：选择题",
        "- 难度：中等",
        "",
        "**题干**",
        "",
        "哪个页面置换算法会淘汰最久未使用的页面？",
        "",
        "**选项**",
        "",
        "- A. FIFO",
        "- B. LRU",
        "- C. Clock",
        "",
      ].join("\n"),
    );
    expect(markdown).not.toMatch(/答案|结果|解析/);
  });

  it("已作答客观题以选项文字输出用户答案、结果、正确答案和解析", () => {
    const markdown = serializeQuizMarkdown(
      "记录",
      [
        quiz({
          id: "answered",
          user_answer: 0,
          correct_answer: 1,
          answer_result: "WRONG",
          answered_at: "2026-08-26T01:00:00Z",
          explanation: "LRU 近似利用局部性原理。",
        }),
      ],
      quizLabels,
    );

    expect(markdown).toContain("**用户答案**\n\nA. FIFO");
    expect(markdown).toContain("**结果**\n\n错误");
    expect(markdown).toContain("**正确答案**\n\nB. LRU");
    expect(markdown).toContain("**解析**\n\nLRU 近似利用局部性原理。");
    expect(markdown).not.toContain("\n\n0\n");
    expect(markdown).not.toContain("\n\n1\n");
  });

  it("多选与填空按可读数组格式输出作答和正确答案", () => {
    const markdown = serializeQuizMarkdown(
      "记录",
      [
        quiz({
          id: "multiple-select",
          question_type: "MULTIPLE_SELECT",
          user_answer: [0, 2],
          correct_answer: [0, 2],
          answer_result: "CORRECT",
          answered_at: "2026-08-31T01:00:00Z",
          explanation: "A 与 C 正确。",
        }),
        quiz({
          id: "fill-blank",
          question_type: "FILL_BLANK",
          stem: "____器负责分配____。",
          options: [],
          user_answer: ["调度", "CPU"],
          correct_answer: [["调度"], ["处理器", "CPU"]],
          answer_result: "CORRECT",
          answered_at: "2026-08-31T01:01:00Z",
          explanation: "调度器负责分配处理器。",
        }),
      ],
      quizLabels,
    );

    expect(markdown).toContain("**用户答案**\n\nA. FIFO、C. Clock");
    expect(markdown).toContain("**正确答案**\n\nA. FIFO、C. Clock");
    expect(markdown).toContain("**用户答案**\n\n第 1 空：调度；第 2 空：CPU");
    expect(markdown).toContain(
      "**正确答案**\n\n第 1 空：调度；第 2 空：处理器 / CPU",
    );
  });

  it.each([
    [null, "待自评"],
    ["CORRECT" as const, "正确"],
  ])("简答题已提交后输出用户答案、参考答案、解析和结果 %s", (result, label) => {
    const markdown = serializeQuizMarkdown(
      "记录",
      [
        quiz({
          id: `short-${result ?? "pending"}`,
          question_type: "SHORT_ANSWER",
          stem: "解释局部性原理。",
          options: [],
          user_answer: "程序倾向访问最近用过或相邻的数据。",
          correct_answer: "时间局部性与空间局部性。",
          explanation: "两类局部性共同提高缓存命中率。",
          answer_result: result,
          answered_at: "2026-08-26T01:00:00Z",
        }),
      ],
      quizLabels,
    );

    expect(markdown).toContain(
      "**用户答案**\n\n程序倾向访问最近用过或相邻的数据。",
    );
    expect(markdown).toContain("**参考答案**\n\n时间局部性与空间局部性。");
    expect(markdown).toContain("**解析**\n\n两类局部性共同提高缓存命中率。");
    expect(markdown).toContain(`**结果**\n\n${label}`);
  });
});

describe("serializeTodoMarkdown", () => {
  it("按 sort_order 混排 ACTIVE AI、手工与被接管项，并过滤 DRAFT/SUPERSEDED", () => {
    const items = selectFormalTodos([
      todo({
        id: "done-ai",
        sort_order: 30,
        content: "完成课后练习",
        status: "DONE",
        source: "AI",
        generation_status: "ACTIVE",
      }),
      todo({
        id: "draft",
        sort_order: 10,
        source: "AI",
        generation_status: "DRAFT",
      }),
      todo({ id: "manual", sort_order: 20, content: "补充手工笔记" }),
      todo({
        id: "taken-over",
        sort_order: 15,
        content: "复习被接管项",
        source: "AI",
        generation_status: null,
      }),
      todo({
        id: "old",
        sort_order: 5,
        source: "AI",
        generation_status: "SUPERSEDED",
      }),
    ]);

    expect(serializeTodoMarkdown("操作系统第一讲", items, "Todo")).toBe(
      [
        "# 操作系统第一讲",
        "",
        "## Todo",
        "",
        "- [ ] 复习被接管项",
        "- [ ] 补充手工笔记",
        "- [x] 完成课后练习",
        "",
      ].join("\n"),
    );
  });

  it("习题与 Todo 的纯文本不会注入标题、链接或原始 HTML", () => {
    const quizMarkdown = serializeQuizMarkdown(
      "记录",
      [
        quiz({
          id: "escaped",
          stem: "# 不是标题，参见 [资料]",
          options: ["<script>", "普通选项", "第三项"],
        }),
      ],
      quizLabels,
    );
    const todoMarkdown = serializeTodoMarkdown(
      "记录",
      [
        todo({
          id: "todo-escaped",
          sort_order: 0,
          content: "# 第一步\n<script>",
        }),
      ],
      "Todo",
    );

    expect(quizMarkdown).toContain("\\# 不是标题，参见 \\[资料\\]");
    expect(quizMarkdown).toContain("A. \\<script\\>");
    expect(quizMarkdown.match(/^# /gm)).toHaveLength(1);
    expect(todoMarkdown).toContain("- [ ] \\# 第一步\n  \\<script\\>");
    expect(todoMarkdown.match(/^# /gm)).toHaveLength(1);
  });
});

describe("serializeAggregateMarkdown", () => {
  const summary = serializeSummaryMarkdown(
    "操作系统第一讲",
    summarySnapshot,
    summaryLabels,
  );
  const knowledgePoints = serializeKnowledgePointsMarkdown(
    "操作系统第一讲",
    [
      {
        name: "进程调度",
        detail: "从就绪队列选择下一个进程。",
        importance: 5,
        tags: [],
      },
    ],
    knowledgePointLabels,
  );
  const quizzes = serializeQuizMarkdown(
    "操作系统第一讲",
    [quiz({ id: "quiz-1" })],
    quizLabels,
  );
  const todos = serializeTodoMarkdown(
    "操作系统第一讲",
    [todo({ id: "todo-1", sort_order: 0 })],
    "Todo",
  );

  it("按 Summary、知识点、习题、Todo 固定顺序合并且只保留一个一级标题", () => {
    const markdown = serializeAggregateMarkdown("操作系统第一讲", [
      summary,
      knowledgePoints,
      quizzes,
      todos,
    ]);

    expect(markdown).not.toBeNull();
    expect(markdown?.match(/^# /gm)).toHaveLength(1);
    expect(markdown).toMatch(
      /## 总结[\s\S]*## 知识点[\s\S]*## 习题[\s\S]*## Todo/,
    );
    expect(markdown).toMatch(/## 总结\n\n[\s\S]*\n\n## 知识点/);
    expect(markdown?.endsWith("\n")).toBe(true);
    expect(markdown).not.toContain("\r");
  });

  it("自然省略缺失资产，不生成空标题", () => {
    const markdown = serializeAggregateMarkdown("操作系统第一讲", [
      summary,
      null,
      null,
      todos,
    ]);

    expect(markdown).toContain("## 总结");
    expect(markdown).toContain("## Todo");
    expect(markdown).not.toMatch(/## 知识点|## 习题|## 复习资料/);
  });

  it("全部资产为空时返回 null，相同输入输出完全一致", () => {
    expect(
      serializeAggregateMarkdown("操作系统第一讲", [null, null, null, null]),
    ).toBeNull();
    expect(serializeAggregateMarkdown("操作系统第一讲", [summary, todos])).toBe(
      serializeAggregateMarkdown("操作系统第一讲", [summary, todos]),
    );
  });
});

describe("纯文本转义", () => {
  it("井号、星号与反引号不会破坏 Markdown 结构，渲染后可见文本不变", () => {
    const markdown = serializeSummaryMarkdown(
      "记录",
      {
        topic: "# 不是一级标题",
        abstract: "普通摘要",
        sections: [
          { heading: "*强调* 与 `代码`", points: ["**加粗**与 __下划线__"] },
        ],
      },
      summaryLabels,
    );

    expect(markdown).toContain("\\# 不是一级标题");
    expect(markdown).toContain("\\*强调\\* 与 \\`代码\\`");
    expect(markdown).toContain("\\*\\*加粗\\*\\*与 \\_\\_下划线\\_\\_");
    // 文档自身的结构标题保持唯一
    expect(markdown.match(/^# /gm)).toHaveLength(1);
    expect(markdown.match(/^## /gm)).toHaveLength(1);
    expect(markdown.match(/^### /gm)).toHaveLength(1);
  });

  it("链接与图片语法保持字面文本", () => {
    const markdown = serializeKnowledgePointsMarkdown(
      "记录",
      [
        {
          name: "带链接的知识点",
          detail: "参见 [文档](https://example.com) 与 ![图片](a.png)",
          importance: 2,
          tags: ["[标签]"],
        },
      ],
      knowledgePointLabels,
    );

    expect(markdown).toContain("参见 \\[文档\\](https://example.com)");
    expect(markdown).toContain("!\\[图片\\](a.png)");
    expect(markdown).toContain("- 标签：\\[标签\\]");
  });

  it("原始 HTML 不会注入文档结构，可见文本保留", () => {
    const markdown = serializeKnowledgePointsMarkdown(
      "记录",
      [
        {
          name: "<script>alert(1)</script>",
          detail: "包含 <b>加粗</b> 与 <img src=x> 的详情",
          importance: 3,
          tags: ["<tag>"],
        },
      ],
      knowledgePointLabels,
    );

    // 全文不存在未转义的 <，原始 HTML 无法进入文档
    expect(markdown).not.toMatch(/(^|[^\\])</);
    expect(markdown).toContain("\\<script\\>alert(1)\\</script\\>");
    expect(markdown).toContain(
      "包含 \\<b\\>加粗\\</b\\> 与 \\<img src=x\\> 的详情",
    );
    expect(markdown).toContain("- 标签：\\<tag\\>");
  });

  it("段落换行不丢失且统一为 LF", () => {
    const markdown = serializeKnowledgePointsMarkdown(
      "记录",
      [
        {
          name: "多行详情",
          detail: "第一段\r\n第二段\n\n第三段",
          importance: 2,
          tags: [],
        },
      ],
      knowledgePointLabels,
    );

    expect(markdown).toContain("第一段\n第二段\n\n第三段");
    expect(markdown).not.toContain("\r");
  });

  it("行首列表、序号、分隔线、代码围栏与表格符号保持纯文本", () => {
    const markdown = serializeTodoMarkdown(
      "记录",
      [
        todo({
          id: "block-markdown",
          sort_order: 0,
          content: [
            "- 子项",
            "+ 另一项",
            "1. 第一步",
            "---",
            "~~~",
            "| A | B |",
            "    四空格不是代码块",
            "\tTab 也不是代码块",
            "  \t混合缩进也不是代码块",
          ].join("\n"),
        }),
      ],
      "Todo",
    );

    expect(markdown).toContain(
      [
        "- [ ] \\- 子项",
        "  \\+ 另一项",
        "  1\\. 第一步",
        "  \\---",
        "  \\~~~",
        "  \\| A \\| B \\|",
        "  &#32;   四空格不是代码块",
        "  &#9;Tab 也不是代码块",
        "    &#9;混合缩进也不是代码块",
      ].join("\n"),
    );
  });
});

describe("buildExportFileName", () => {
  it.each([
    ["操作系统第一讲", "总结", "操作系统第一讲-总结.md"],
    ["含空格 标题", "知识点", "含空格 标题-知识点.md"],
  ])("默认名拼接 %s-%s.md", (title, assetLabel, expected) => {
    expect(buildExportFileName(title, assetLabel, "未命名学习记录")).toBe(
      expected,
    );
  });

  it.each([
    ['a<b>:"/\\|?*b', "abb-总结.md"],
    ["隐藏\u0000控制\u007F字符", "隐藏控制字符-总结.md"],
    ["尾部点与空格..  ", "尾部点与空格-总结.md"],
    ["???", "未命名学习记录-总结.md"],
    ["   ", "未命名学习记录-总结.md"],
  ])("清理 Windows 非法输入：%s", (title, expected) => {
    expect(buildExportFileName(title, "总结", "未命名学习记录")).toBe(expected);
  });

  it("清理后的完整名称命中设备保留名时回退未命名", () => {
    expect(buildExportFileName("CON", "", "未命名学习记录")).toBe(
      "未命名学习记录.md",
    );
    expect(buildExportFileName("com1", "", "未命名学习记录")).toBe(
      "未命名学习记录.md",
    );
  });

  it("空标题复用未命名学习记录文案", () => {
    expect(buildExportFileName("", "知识点", "未命名学习记录")).toBe(
      "未命名学习记录-知识点.md",
    );
  });
});
