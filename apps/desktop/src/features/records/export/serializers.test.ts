import { describe, expect, it } from "vitest";
import {
  buildExportFileName,
  serializeKnowledgePointsMarkdown,
  serializeSummaryMarkdown,
} from "@/features/records/export/serializers";

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
