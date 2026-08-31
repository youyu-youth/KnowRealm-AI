/**
 * PROTOTYPE — 模拟测试卷面原型 v2（throwaway：不接后端、状态仅在内存、硬编码文案）
 *
 * 问题：模拟测试的卷面（作答页 / 结果页）应该长什么样？
 * 二轮改进（用户反馈）：
 *   1. 题目翻页展示（不再整卷一页滚动），且展示形式可由作答者随时切换：
 *      单题（一页一题，键盘 ←→ 翻题）/ 分段（一屏一个大题）/ 整卷（连续滚动）
 *   2. 题型不受记录习题（单选/判断/简答）约束，模拟测试卷演示五种题型：
 *      单选、多选、判断、填空、简答
 * URL search 参数：
 *   /prototype-mock-test?scenario=answering&view=single|sectioned|full
 * 场景：entry（课程页入口）/ answering / grading / result
 * 定稿语义保持（15-mock-test.md）：逐题提交一题一答、全部答完才可交卷、
 * 简答 AI 评分依据必存、低置信（<0.7）只读标记"建议人工复核"、
 * 评分失败题排除出分母。
 * 开放问题（反馈捕获时拍板）：多选/填空等新题型的题目来源——
 * 08 生成扩五型 vs 组卷时 AI 生成。原型只演示卷面形态。
 * 底部浮条仅 DEV 构建可见，非页面设计的一部分。
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Check, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

/* ---------------------------------- mock 数据（五题型） ---------------------------------- */

type McQuestion = {
  id: number; kind: "mc"; type: "单选";
  stem: string; options: string[]; correctIndex: number; explanation: string;
};
type MrQuestion = {
  id: number; kind: "mr"; type: "多选";
  stem: string; options: string[]; correctIndices: number[]; explanation: string;
};
type TfQuestion = {
  id: number; kind: "tf"; type: "判断";
  stem: string; options: [string, string]; correctIndex: number; explanation: string;
};
type FbBlank = { answers: string[] };
type FbQuestion = {
  id: number; kind: "fb"; type: "填空";
  /** 题干中 "____" 为空位占位，与 blanks 一一对应 */
  stem: string; blanks: FbBlank[]; explanation: string;
};
type ShortGrade =
  | { status: "ok"; verdict: "CORRECT" | "PARTIAL" | "WRONG"; score: number; confidence: number; rationale: string }
  | { status: "failed"; errorCode: string };
type ShortQuestion = {
  id: number; kind: "short"; type: "简答";
  stem: string; reference: string; grade: ShortGrade;
};
type MockQuestion = McQuestion | MrQuestion | TfQuestion | FbQuestion | ShortQuestion;

/** 部署级配置常量（原型内 mock，对应 SHORT_ANSWER_REVIEW_THRESHOLD） */
const REVIEW_THRESHOLD = 0.7;

const COURSE_NAME = "线性代数";
const EXAM_NO = 3;

const QUESTIONS: MockQuestion[] = [
  { id: 1, kind: "mc", type: "单选", stem: "设 A 为 3 阶方阵，det(A) = 2，则 det(2A) = ？", options: ["4", "8", "16", "24"], correctIndex: 2, explanation: "det(kA) = kⁿdet(A)，n = 3，故 2³ × 2 = 16。" },
  { id: 2, kind: "mc", type: "单选", stem: "若 n 阶方阵 A 可逆，则 A 的秩 r(A) = ？", options: ["0", "1", "n − 1", "n"], correctIndex: 3, explanation: "可逆 ⟺ 行列式非零 ⟺ 满秩，r(A) = n。" },
  { id: 3, kind: "mc", type: "单选", stem: "n 阶方阵全部特征值之和等于？", options: ["行列式", "迹（主对角元之和）", "秩", "特征值的个数"], correctIndex: 1, explanation: "特征多项式各根之和等于迹 tr(A)。" },
  { id: 4, kind: "mc", type: "单选", stem: "齐次线性方程组 Ax = 0（A 为 m×n）存在非零解的充要条件是？", options: ["m < n", "r(A) < n", "r(A) < m", "det(A) = 0"], correctIndex: 1, explanation: "存在非零解 ⟺ n − r(A) > 0 ⟺ r(A) < n。" },
  { id: 5, kind: "mc", type: "单选", stem: "实对称矩阵的不同特征值对应的特征向量？", options: ["线性相关", "正交", "相等", "无关但未必正交"], correctIndex: 1, explanation: "实对称矩阵属于不同特征值的特征向量相互正交。" },
  { id: 6, kind: "mc", type: "单选", stem: "若 λ 是 A 的特征值，则 A² 的一个特征值是？", options: ["λ", "λ²", "2λ", "√λ"], correctIndex: 1, explanation: "Ax = λx ⟹ A²x = λ²x。" },
  {
    id: 7, kind: "mr", type: "多选",
    stem: "下列矩阵中属于正交矩阵的有？",
    options: ["单位矩阵 E", "坐标旋转矩阵 [[cosθ, −sinθ],[sinθ, cosθ]]", "置换矩阵 [[0,1],[1,0]]", "投影矩阵 [[1,0],[0,0]]"],
    correctIndices: [0, 1, 2], explanation: "前三者均满足 AᵀA = E；投影矩阵不满足（第 4 个选项错误）。",
  },
  {
    id: 8, kind: "mr", type: "多选",
    stem: "下列关于 n 阶可逆方阵的命题，正确的有？",
    options: ["det(A) ≠ 0", "r(A) = n", "行向量组线性无关", "特征值全为 1"],
    correctIndices: [0, 1, 2], explanation: "前三者均为可逆的等价刻画；特征值全为 1 与可逆无关（第 4 个选项错误）。",
  },
  {
    id: 9, kind: "mr", type: "多选",
    stem: "关于方阵 A 的特征值 λ₁,…,λₙ，下列说法正确的有？",
    options: ["λ = 0 是特征值 ⟺ A 不可逆", "互异特征值对应的特征向量线性无关", "λ₁ + ⋯ + λₙ = tr(A)", "λ₁⋯λₙ = det(A)"],
    correctIndices: [0, 1, 2, 3], explanation: "四条均为特征值的基本性质，全部正确。",
  },
  {
    id: 10, kind: "mr", type: "多选",
    stem: "下列向量组中线性无关的有？",
    options: ["(1,0,0)、(0,1,0)、(0,0,1)", "(1,2)、(2,4)", "(1,1,0)、(0,1,1)", "(1,0)、(0,1)、(1,1)"],
    correctIndices: [0, 2], explanation: "标准单位向量组与 (1,1,0)、(0,1,1) 无关；(2,4)=2(1,2) 相关，三个二维向量必相关。",
  },
  { id: 11, kind: "tf", type: "判断", stem: "若 A、B 都可逆，则 AB 也可逆，且 (AB)⁻¹ = B⁻¹A⁻¹。", options: ["对", "错"], correctIndex: 0, explanation: "乘积可逆且逆的顺序反转，命题正确。" },
  { id: 12, kind: "tf", type: "判断", stem: "秩相等的两个同型矩阵必等价。", options: ["对", "错"], correctIndex: 0, explanation: "同型矩阵等价 ⟺ 秩相等，命题正确。" },
  { id: 13, kind: "tf", type: "判断", stem: "正交矩阵的特征值必为实数。", options: ["对", "错"], correctIndex: 1, explanation: "正交矩阵特征值的模为 1，但可以是复数（如旋转矩阵），命题错误。" },
  { id: 14, kind: "tf", type: "判断", stem: "对称矩阵必可与对角矩阵相似。", options: ["对", "错"], correctIndex: 0, explanation: "实对称矩阵必可正交对角化，命题正确。" },
  {
    id: 15, kind: "fb", type: "填空",
    stem: "设 A 为 3 阶方阵且 det(A) = 2，则 det(2A) = ____，det(A⁻¹) = ____。",
    blanks: [{ answers: ["16"] }, { answers: ["1/2", "0.5"] }],
    explanation: "det(2A) = 2³·2 = 16；det(A⁻¹) = 1/det(A) = 1/2。",
  },
  {
    id: 16, kind: "fb", type: "填空",
    stem: "A 为 3×4 矩阵，r(A) = 2，则齐次方程组 Ax = 0 的基础解系含 ____ 个解向量。",
    blanks: [{ answers: ["2", "二", "两"] }],
    explanation: "基础解系维数 = n − r(A) = 4 − 2 = 2。",
  },
  {
    id: 17, kind: "fb", type: "填空",
    stem: "矩阵 [[1,2],[3,x]] 的秩为 2，当且仅当 x ____ 6。（填 >、<、≠ 之一）",
    blanks: [{ answers: ["≠", "不等于"] }],
    explanation: "det = x − 6 ≠ 0 ⟺ x ≠ 6。",
  },
  {
    id: 18, kind: "short", type: "简答",
    stem: "叙述矩阵秩的定义，并说明它与向量组线性相关性之间的关系。",
    reference: "矩阵的秩为其行（列）向量组的极大线性无关组所含向量个数，也等于最高阶非零子式的阶数。若向量组秩小于向量个数则线性相关，等于则线性无关。",
    grade: { status: "ok", verdict: "CORRECT", score: 0.88, confidence: 0.55, rationale: "作答准确定义了极大线性无关组与秩的关系，并正确指出等价于最高阶非零子式的阶数；与向量个数比较判定相关性的结论表述完整。对投影系数公式的书写略有跳步。" },
  },
  {
    id: 19, kind: "short", type: "简答",
    stem: "证明：正交矩阵的特征值的模必为 1。",
    reference: "设 Ax = λx（x ≠ 0）。由 A 正交知 ‖Ax‖ = ‖x‖，故 |λ|·‖x‖ = ‖x‖，得 |λ| = 1。",
    grade: { status: "ok", verdict: "PARTIAL", score: 0.5, confidence: 0.82, rationale: "正确使用了正交变换保持范数不变这一关键性质，但未说明 ‖x‖ ≠ 0 从而两边约去的依据，且结尾未明确写出 |λ| = 1 的结论，论证链条不完整。" },
  },
  {
    id: 20, kind: "short", type: "简答",
    stem: "叙述施密特（Schmidt）正交化的过程，并说明其用途。",
    reference: "从线性无关向量组出发，逐个减去在已得正交向量上的投影分量，得到两两正交的向量组；再单位化得标准正交组。用途：构造标准正交基，用于正交对角化、QR 分解等。",
    grade: { status: "failed", errorCode: "PROVIDER_REQUEST_FAILED" },
  },
];

const SECTIONS = [
  { key: "mc", title: "一、单项选择题", ids: QUESTIONS.filter((q) => q.kind === "mc").map((q) => q.id) },
  { key: "mr", title: "二、多项选择题", ids: QUESTIONS.filter((q) => q.kind === "mr").map((q) => q.id) },
  { key: "tf", title: "三、判断题", ids: QUESTIONS.filter((q) => q.kind === "tf").map((q) => q.id) },
  { key: "fb", title: "四、填空题", ids: QUESTIONS.filter((q) => q.kind === "fb").map((q) => q.id) },
  { key: "short", title: "五、简答题", ids: QUESTIONS.filter((q) => q.kind === "short").map((q) => q.id) },
] as const;

const TYPE_LABEL: Record<MockQuestion["kind"], string> = { mc: "单选", mr: "多选", tf: "判断", fb: "填空", short: "简答" };

type Answer = { choice?: number; choices?: number[]; blanks?: string[]; text?: string };

/** URL 直达评分中/结果场景时使用的演示作答（客观错 2 题、填空半对 1 题） */
const DEMO_ANSWERS: Record<number, Answer> = Object.fromEntries(
  QUESTIONS.map((q) => {
    if (q.kind === "short") return [q.id, { text: "（演示作答）按参考答案方向的完整表述，共三段。" }];
    if (q.kind === "mr") {
      const wrong: Record<number, number[]> = { 10: [0, 1] };
      return [q.id, { choices: wrong[q.id] ?? q.correctIndices }];
    }
    if (q.kind === "fb") {
      const demo: Record<number, string[]> = { 15: ["16", "2"], 16: ["2"], 17: ["≠"] };
      return [q.id, { blanks: demo[q.id] ?? q.blanks.map((b) => b.answers[0] ?? "") }];
    }
    const wrong: Record<number, number> = { 3: 0 };
    return [q.id, { choice: wrong[q.id] ?? q.correctIndex }];
  }),
);

/* ---------------------------------- 路由与搜索参数 ---------------------------------- */

const VIEWS = [
  { key: "single", name: "单题" },
  { key: "sectioned", name: "分段" },
  { key: "full", name: "整卷" },
] as const;
type ViewKey = (typeof VIEWS)[number]["key"];

const SCENARIOS = [
  { key: "entry", name: "入口" },
  { key: "answering", name: "作答中" },
  { key: "grading", name: "评分中" },
  { key: "result", name: "结果" },
] as const;
type ScenarioKey = (typeof SCENARIOS)[number]["key"];

function asView(value: unknown): ViewKey {
  return VIEWS.some((v) => v.key === value) ? (value as ViewKey) : "single";
}
function asScenario(value: unknown): ScenarioKey {
  return SCENARIOS.some((s) => s.key === value) ? (value as ScenarioKey) : "entry";
}

export const Route = createFileRoute("/prototype-mock-test")({
  validateSearch: (search: Record<string, unknown>): { scenario: ScenarioKey; view: ViewKey } => ({
    scenario: asScenario(search.scenario),
    view: asView(search.view),
  }),
  component: PrototypeMockTestRoute,
});

export function PrototypeMockTestRoute() {
  const { scenario, view } = Route.useSearch();
  const navigate = useNavigate();
  const patchSearch = useCallback(
    (patch: { scenario?: ScenarioKey; view?: ViewKey }) => {
      void navigate({
        to: "/prototype-mock-test",
        search: { scenario: patch.scenario ?? scenario, view: patch.view ?? view },
        replace: true,
      });
    },
    [navigate, scenario, view],
  );

  return (
    <>
      {scenario === "entry" ? <EntryScenario /> : <ExamPaper key={scenario} scenario={scenario} view={view} onPatch={patchSearch} />}
      <PrototypeBar scenario={scenario} view={view} onPatch={patchSearch} />
    </>
  );
}

/* ---------------------------------- 浮动切换条（仅 DEV） ---------------------------------- */

function PrototypeBar({
  scenario,
  view,
  onPatch,
}: {
  scenario: ScenarioKey;
  view: ViewKey;
  onPatch: (patch: { scenario?: ScenarioKey; view?: ViewKey }) => void;
}) {
  if (!import.meta.env.DEV) return null;
  const viewName = VIEWS.find((v) => v.key === view)?.name ?? view;

  return (
    <div className="fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-lg bg-ink-strong px-3 py-2 text-paper shadow-lg">
      <span className="text-label min-w-16 text-center">形式：{viewName}</span>
      <div className="bg-surface-strong/40 h-5 w-px" />
      <div className="flex items-center gap-1">
        {SCENARIOS.map((s) => (
          <button
            key={s.key}
            type="button"
            className={`text-label cursor-pointer rounded-xs px-2 py-1 transition-colors ${
              scenario === s.key ? "bg-paper text-ink-strong" : "hover:bg-surface-strong/30"
            }`}
            onClick={() => onPatch({ scenario: s.key })}
          >
            {s.name}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------- 场景：课程页入口 ---------------------------------- */

function EntryScenario() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(20);
  const [types, setTypes] = useState({ mc: true, mr: true, tf: true, fb: true, short: true });

  const history = [
    { no: 3, state: "IN_PROGRESS", answered: 12, total: 20, at: "2026-08-31 09:12" },
    { no: 2, state: "COMPLETED", score: 78, at: "2026-08-28 20:40" },
    { no: 1, state: "COMPLETED", score: 65, at: "2026-08-25 15:02" },
  ] as const;

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col py-8">
      <Button
        variant="ghost"
        className="text-muted-foreground -ml-3 cursor-pointer self-start"
        onClick={() => window.history.back()}
      >
        <ArrowLeft className="size-4" /> 返回课程列表
      </Button>
      <div className="mt-6">
        <h1 className="text-headline font-headline text-ink-strong">{COURSE_NAME}</h1>
        <p className="text-body text-muted-foreground mt-2">学业 · 本科 · 大一</p>
      </div>
      <div className="mt-6 flex gap-5">
        {["概览", "学习记录", "模拟测试"].map((tab) => (
          <span
            key={tab}
            className={`text-section font-section cursor-default pb-2 ${
              tab === "模拟测试" ? "text-ink-strong border-b-2 border-ink-strong" : "text-muted-foreground"
            }`}
          >
            {tab}
          </span>
        ))}
      </div>

      <div className="mt-8 flex items-center justify-between">
        <h2 className="text-section font-section text-ink">历史测试</h2>
        <Button className="cursor-pointer" onClick={() => setOpen(true)}>
          开始模拟测试
        </Button>
      </div>

      <ul aria-label="历史测试列表" className="mt-3">
        {history.map((h) => (
          <li key={h.no} className="border-border min-w-0 border-b py-4 last:border-b-0">
            <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-4">
              <div className="min-w-0">
                <p className="text-body font-section text-ink truncate">
                  第 {h.no} 次模拟测试
                  {h.state === "IN_PROGRESS" && <span className="text-learning ml-2">进行中 · 已答 {h.answered}/{h.total}</span>}
                </p>
                <p className="text-label text-muted-foreground mt-1.5">
                  {h.at} · 20 题 · {h.state === "COMPLETED" ? `得分 ${h.score}` : "未交卷"}
                </p>
              </div>
              {h.state === "IN_PROGRESS" ? (
                <Button
                  variant="outline"
                  className="cursor-pointer"
                  onClick={() =>
                    void navigate({ to: "/prototype-mock-test", search: { scenario: "answering", view: "single" } })
                  }
                >
                  继续作答
                </Button>
              ) : (
                <span className="text-label text-muted-foreground tabular-nums">{h.score} 分</span>
              )}
            </div>
          </li>
        ))}
      </ul>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>开始模拟测试</DialogTitle>
          </DialogHeader>
          <div className="mt-2 space-y-5">
            <div>
              <p className="text-section font-section text-ink">题量</p>
              <RadioGroup
                className="mt-2 flex gap-5"
                value={String(count)}
                onValueChange={(v) => setCount(Number(v))}
              >
                {[5, 10, 20].map((n) => (
                  <Field key={n} orientation="horizontal">
                    <RadioGroupItem id={`count-${n}`} value={String(n)} />
                    <FieldLabel htmlFor={`count-${n}`}>{n} 题</FieldLabel>
                  </Field>
                ))}
              </RadioGroup>
            </div>
            <div>
              <p className="text-section font-section text-ink">题型</p>
              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2">
                {([["mc", "单选题"], ["mr", "多选题"], ["tf", "判断题"], ["fb", "填空题"], ["short", "简答题"]] as const).map(
                  ([key, label]) => (
                    <Field key={key} orientation="horizontal">
                      <Checkbox
                        id={`type-${key}`}
                        checked={types[key]}
                        onCheckedChange={(checked) => setTypes((prev) => ({ ...prev, [key]: checked === true }))}
                      />
                      <FieldLabel htmlFor={`type-${key}`}>{label}</FieldLabel>
                    </Field>
                  ),
                )}
              </div>
            </div>
            <p className="text-label text-muted-foreground bg-surface-subtle rounded-xs px-3 py-2">
              题库现有 20 道已采纳习题满足所选条件，将随机抽题组卷。
            </p>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="ghost" className="cursor-pointer" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button
              className="cursor-pointer"
              onClick={() => {
                setOpen(false);
                void navigate({ to: "/prototype-mock-test", search: { scenario: "answering", view: "single" } });
              }}
            >
              开始测试
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

/* ---------------------------------- 考试状态 ---------------------------------- */

type ExamPhase = "answering" | "grading" | "result";
/** 卷面只接收非入口场景 */
type PaperScenario = Exclude<ScenarioKey, "entry">;

function useExamState(urlScenario: PaperScenario) {
  const [answers, setAnswers] = useState<Record<number, Answer>>({});
  const [phase, setPhase] = useState<ExamPhase>("answering");
  const [confirmOpen, setConfirmOpen] = useState(false);

  const answeredCount = QUESTIONS.filter((q) => answers[q.id] !== undefined).length;
  const answeredAll = answeredCount === QUESTIONS.length;

  /** URL 场景直达（未经过作答）时使用演示作答；用户真实作答后以真实数据为准 */
  const effective: Record<number, Answer> = useMemo(
    () => (answeredCount === 0 ? DEMO_ANSWERS : answers),
    [answers, answeredCount],
  );
  const scenario: ExamPhase = urlScenario === "answering" ? phase : urlScenario;

  const setAnswer = useCallback((id: number, value: Answer) => {
    setAnswers((prev) => ({ ...prev, [id]: value }));
  }, []);

  const submitExam = useCallback(() => {
    setConfirmOpen(false);
    setPhase("grading");
    window.setTimeout(() => setPhase("result"), 2200);
  }, []);

  const restart = useCallback(() => {
    setAnswers({});
    setPhase("answering");
  }, []);

  return {
    answers, effective, answeredCount, answeredAll,
    scenario, confirmOpen, setConfirmOpen, setAnswer, submitExam, restart,
  };
}

type Exam = ReturnType<typeof useExamState>;

const qById = (id: number) => QUESTIONS.find((q) => q.id === id) as MockQuestion;

/* ---------------------------------- 结果计算（多选全对才得分；填空按空计分） ---------------------------------- */

type Review = {
  verdict: "CORRECT" | "WRONG" | "PARTIAL" | "UNSCORED";
  lowConfidence: boolean;
};

function blankOk(q: FbQuestion, answer: Answer | undefined, blankIndex: number) {
  const filled = answer?.blanks?.[blankIndex]?.trim();
  if (filled === undefined || filled === "") return false;
  return q.blanks[blankIndex].answers.some((a) => a === filled);
}

function verdictOf(q: MockQuestion, answer: Answer | undefined): Review {
  if (q.kind === "short") {
    if (q.grade.status === "failed") return { verdict: "UNSCORED", lowConfidence: false };
    return { verdict: q.grade.verdict, lowConfidence: q.grade.confidence < REVIEW_THRESHOLD };
  }
  if (q.kind === "mr") {
    const chosen = answer?.choices ?? [];
    const same =
      chosen.length === q.correctIndices.length && q.correctIndices.every((i) => chosen.includes(i));
    return { verdict: same ? "CORRECT" : "WRONG", lowConfidence: false };
  }
  if (q.kind === "fb") {
    const okCount = q.blanks.filter((_, i) => blankOk(q, answer, i)).length;
    const verdict = okCount === q.blanks.length ? "CORRECT" : okCount > 0 ? "PARTIAL" : "WRONG";
    return { verdict, lowConfidence: false };
  }
  return { verdict: answer?.choice === q.correctIndex ? "CORRECT" : "WRONG", lowConfidence: false };
}

function objectiveScore(q: MockQuestion, answer: Answer | undefined) {
  if (q.kind === "short") return q.grade.status === "ok" ? q.grade.score : 0;
  if (q.kind === "fb") {
    const ok = q.blanks.filter((_, i) => blankOk(q, answer, i)).length;
    return q.blanks.length === 0 ? 0 : ok / q.blanks.length;
  }
  return verdictOf(q, answer).verdict === "CORRECT" ? 1 : 0;
}

function computeResult(effective: Record<number, Answer>) {
  let scoreSum = 0;
  let counted = 0;
  let correct = 0;
  let wrong = 0;
  let partial = 0;
  let unscored = 0;
  let review = 0;
  for (const q of QUESTIONS) {
    const v = verdictOf(q, effective[q.id]);
    if (v.verdict === "UNSCORED") {
      unscored += 1;
      continue;
    }
    counted += 1;
    if (v.verdict === "CORRECT") correct += 1;
    if (v.verdict === "WRONG") wrong += 1;
    if (v.verdict === "PARTIAL") partial += 1;
    if (v.lowConfidence) review += 1;
    scoreSum += objectiveScore(q, effective[q.id]);
  }
  return {
    score100: counted === 0 ? 0 : Math.round((scoreSum / counted) * 100),
    counted, correct, wrong, partial, unscored, review,
  };
}

/* ---------------------------------- 共享原子 ---------------------------------- */

function VerdictTag({ verdict }: { verdict: Review["verdict"] }) {
  const map = {
    CORRECT: { text: "答对", cls: "text-success-foreground bg-success-soft", dot: "bg-success-foreground" },
    WRONG: { text: "答错", cls: "text-destructive bg-destructive/10", dot: "bg-destructive" },
    PARTIAL: { text: "半对", cls: "text-warning-foreground bg-warning-soft", dot: "bg-warning-foreground" },
    UNSCORED: { text: "未计分", cls: "text-muted-foreground bg-surface-subtle", dot: "bg-muted-foreground" },
  } as const;
  const m = map[verdict];
  return (
    <span className={`text-label inline-flex items-center gap-1.5 rounded-xs px-1.5 py-0.5 ${m.cls}`}>
      <span className={`size-1.5 rounded-full ${m.dot}`} />
      {m.text}
    </span>
  );
}

function ReviewFlag() {
  return (
    <span className="text-label text-warning-foreground bg-warning-soft inline-flex items-center gap-1.5 rounded-xs px-1.5 py-0.5">
      <span className="bg-warning-foreground size-1.5 rounded-full" />
      建议人工复核
    </span>
  );
}

/* ---------------------------------- 作答控件（五题型） ---------------------------------- */

function McAnswerBlock({ q, answer, locked, onAnswer }: { q: McQuestion | TfQuestion; answer: Answer | undefined; locked: boolean; onAnswer: (id: number, v: Answer) => void }) {
  return (
    <RadioGroup
      className="mt-3 grid gap-2"
      value={answer?.choice === undefined ? "" : String(answer.choice)}
      disabled={locked}
      onValueChange={(v) => onAnswer(q.id, { choice: Number(v) })}
    >
      {q.options.map((option, index) => {
        const id = `proto-q${q.id}-o${index}`;
        return (
          <Field key={id} orientation="horizontal">
            <RadioGroupItem id={id} value={String(index)} />
            <FieldLabel htmlFor={id} className="text-body font-body text-ink cursor-pointer">
              {option}
            </FieldLabel>
          </Field>
        );
      })}
    </RadioGroup>
  );
}

function MrAnswerBlock({ q, answer, locked, onAnswer }: { q: MrQuestion; answer: Answer | undefined; locked: boolean; onAnswer: (id: number, v: Answer) => void }) {
  const [draft, setDraft] = useState<number[]>([]);
  const submitted = answer?.choices !== undefined;
  const current: number[] = submitted ? (answer?.choices ?? []) : draft;
  const toggle = (index: number, checked: boolean) => {
    const next = checked ? [...current, index].sort((a, b) => a - b) : current.filter((i) => i !== index);
    if (submitted || locked) return;
    setDraft(next);
  };
  return (
    <div className="mt-3">
      <div className="grid gap-2">
        {q.options.map((option, index) => {
          const id = `proto-q${q.id}-o${index}`;
          return (
            <Field key={id} orientation="horizontal">
              <Checkbox
                id={id}
                disabled={submitted || locked}
                checked={current.includes(index)}
                onCheckedChange={(checked) => toggle(index, checked === true)}
              />
              <FieldLabel htmlFor={id} className="text-body font-body text-ink cursor-pointer">
                {option}
              </FieldLabel>
            </Field>
          );
        })}
      </div>
      {!submitted && (
        <Button
          variant="outline"
          size="sm"
          className="mt-2 cursor-pointer disabled:cursor-not-allowed"
          disabled={locked || draft.length === 0}
          onClick={() => onAnswer(q.id, { choices: draft })}
        >
          提交作答
        </Button>
      )}
      {submitted && <p className="text-label text-muted-foreground mt-2">已提交 · 一题一答，不可修改</p>}
    </div>
  );
}

function FbAnswerBlock({ q, answer, locked, onAnswer }: { q: FbQuestion; answer: Answer | undefined; locked: boolean; onAnswer: (id: number, v: Answer) => void }) {
  const [draft, setDraft] = useState<string[]>(() => q.blanks.map(() => ""));
  const submitted = answer?.blanks !== undefined;
  const values: string[] = submitted ? (answer?.blanks ?? []) : draft;
  const parts = q.stem.split("____");
  return (
    <div className="mt-3">
      <p className="text-body text-ink leading-8">
        {parts.map((part, index) => (
          <span key={index}>
            {part}
            {index < q.blanks.length && (
              <input
                aria-label={`第 ${q.id} 题第 ${index + 1} 空`}
                className="text-body font-body text-ink-strong border-ink/40 mx-2 w-28 border-b bg-transparent px-1 py-0.5 text-center outline-none focus:border-ink disabled:border-border disabled:text-muted-foreground"
                disabled={submitted || locked}
                value={values[index]}
                onChange={(e) =>
                  setDraft((prev) => prev.map((v, i) => (i === index ? e.target.value : v)))
                }
              />
            )}
          </span>
        ))}
      </p>
      {!submitted && (
        <Button
          variant="outline"
          size="sm"
          className="mt-2 cursor-pointer disabled:cursor-not-allowed"
          disabled={locked || draft.some((v) => v.trim() === "")}
          onClick={() => onAnswer(q.id, { blanks: draft })}
        >
          提交作答
        </Button>
      )}
      {submitted && <p className="text-label text-muted-foreground mt-2">已提交 · 一题一答，不可修改</p>}
    </div>
  );
}

function ShortAnswerBlock({ q, answer, locked, onAnswer }: { q: ShortQuestion; answer: Answer | undefined; locked: boolean; onAnswer: (id: number, v: Answer) => void }) {
  const [draft, setDraft] = useState("");
  const submitted = answer?.text !== undefined;
  return (
    <div className="mt-3">
      <Textarea
        value={submitted ? answer.text : draft}
        disabled={submitted || locked}
        maxLength={2000}
        rows={4}
        placeholder="对照参考作答自由表述，提交后锁定"
        onChange={(e) => setDraft(e.target.value)}
        aria-label={`第 ${q.id} 题作答`}
      />
      {!submitted && (
        <Button
          variant="outline"
          size="sm"
          className="mt-2 cursor-pointer disabled:cursor-not-allowed"
          disabled={locked || draft.trim().length === 0}
          onClick={() => onAnswer(q.id, { text: draft })}
        >
          提交作答
        </Button>
      )}
      {submitted && <p className="text-label text-muted-foreground mt-2">已提交 · 一题一答，不可修改</p>}
    </div>
  );
}

function QuestionAnswerArea({ q, exam }: { q: MockQuestion; exam: Exam }) {
  const answer = exam.answers[q.id];
  const locked = answer !== undefined;
  const common = { answer, locked: locked || exam.scenario !== "answering", onAnswer: exam.setAnswer };
  switch (q.kind) {
    case "mc":
    case "tf":
      return <McAnswerBlock q={q} {...common} />;
    case "mr":
      return <MrAnswerBlock q={q} {...common} />;
    case "fb":
      return <FbAnswerBlock q={q} {...common} />;
    case "short":
      return <ShortAnswerBlock q={q} {...common} />;
  }
}

/* ---------------------------------- 批改展示（五题型） ---------------------------------- */

function ObjectiveReview({ q, answer }: { q: McQuestion | MrQuestion | TfQuestion | FbQuestion; answer: Answer | undefined }) {
  const v = verdictOf(q, answer);
  let yours = "未作答";
  let correct = "";
  if (q.kind === "mc" || q.kind === "tf") {
    yours = answer?.choice === undefined ? "未作答" : q.options[answer.choice];
    correct = q.options[q.correctIndex];
  } else if (q.kind === "mr") {
    yours = (answer?.choices ?? []).map((i) => q.options[i]).join("、") || "未作答";
    correct = q.correctIndices.map((i) => q.options[i]).join("、");
  }
  return (
    <div className="border-border mt-3 space-y-2 border-t pt-3">
      <div className="text-label text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <VerdictTag verdict={v.verdict} />
        {q.kind !== "fb" && (
          <>
            <span>你的作答：{yours}</span>
            <span>正确答案：{correct}</span>
          </>
        )}
      </div>
      {q.kind === "fb" && (
        <div className="space-y-1">
          {q.blanks.map((blank, index) => {
            const ok = blankOk(q, answer, index);
            const filled = answer?.blanks?.[index]?.trim() || "（空）";
            return (
              <p key={index} className="text-label text-muted-foreground tabular-nums">
                第 {index + 1} 空：
                <span className={ok ? "text-success-foreground" : "text-destructive"}>{filled}</span>
                {ok ? " ✓" : <span className="text-destructive"> ✗（应为 {blank.answers[0]}）</span>}
              </p>
            );
          })}
        </div>
      )}
      <p className="text-body-dense text-ink">解析：{q.explanation}</p>
    </div>
  );
}

function ShortReview({ q, answer }: { q: ShortQuestion; answer: Answer | undefined }) {
  return (
    <div className="border-border mt-3 space-y-2 border-t pt-3">
      <p className="text-body-dense text-ink">
        你的作答：<span className="text-muted-foreground">{answer?.text ?? "未作答"}</span>
      </p>
      {q.grade.status === "failed" ? (
        <div className="bg-surface-subtle space-y-1 rounded-xs px-3 py-2.5">
          <p className="text-label text-muted-foreground">评分失败（{q.grade.errorCode}）· 未计分</p>
          <p className="text-label text-muted-foreground">作答已保存；本次成绩不含此题，可再考一张新卷。</p>
        </div>
      ) : (
        <div className="bg-surface-subtle space-y-1.5 rounded-xs px-3 py-2.5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <VerdictTag verdict={q.grade.verdict} />
            <span className="text-label text-muted-foreground tabular-nums">得分 {q.grade.score.toFixed(2)}</span>
            <span className="text-label text-muted-foreground tabular-nums">置信度 {q.grade.confidence.toFixed(2)}</span>
            {q.grade.confidence < REVIEW_THRESHOLD && <ReviewFlag />}
          </div>
          <p className="text-body-dense text-ink">评分依据：{q.grade.rationale}</p>
          <p className="text-label text-muted-foreground">参考答案：{q.reference}</p>
        </div>
      )}
    </div>
  );
}

function QuestionReview({ q, answer }: { q: MockQuestion; answer: Answer | undefined }) {
  return q.kind === "short" ? <ShortReview q={q} answer={answer} /> : <ObjectiveReview q={q} answer={answer} />;
}

/* ---------------------------------- 交卷与评分 ---------------------------------- */

function SubmitDialog({ exam }: { exam: Exam }) {
  return (
    <Dialog open={exam.confirmOpen} onOpenChange={exam.setConfirmOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>确认交卷？</DialogTitle>
        </DialogHeader>
        <p className="text-body text-muted-foreground mt-2">
          共 {QUESTIONS.length} 题，已答 {exam.answeredCount} 题。客观题立即判分，简答题由 AI
          评分；交卷后作答不可再修改。
        </p>
        <DialogFooter className="mt-4">
          <Button variant="ghost" className="cursor-pointer" onClick={() => exam.setConfirmOpen(false)}>
            继续作答
          </Button>
          <Button className="cursor-pointer" onClick={exam.submitExam}>
            确认交卷
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function GradingScreen() {
  return (
    <div className="work-surface-enter max-w-reading px-content mx-auto flex min-h-full flex-col items-center justify-center py-16">
      <Spinner className="text-ink-strong size-6" />
      <p className="text-section font-section text-ink mt-5">正在评分…</p>
      <p className="text-label text-muted-foreground mt-2">客观题已判分完成，简答题逐题评分中（通常数秒）</p>
      <div className="border-border mt-6 w-full max-w-sm border-t pt-4">
        {QUESTIONS.filter((q) => q.kind === "short").map((q, index) => (
          <p key={q.id} className="text-label text-muted-foreground flex items-center justify-between py-1.5 tabular-nums">
            <span>第 {q.id} 题 · 简答</span>
            {index < 2 ? <span className="text-success-foreground">评分完成</span> : <span>评分中</span>}
          </p>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------- 卷面主体（侧栏 + 三种展示形式） ---------------------------------- */

function ExamPaper({
  scenario,
  view,
  onPatch,
}: {
  scenario: PaperScenario;
  view: ViewKey;
  onPatch: (patch: { scenario?: ScenarioKey; view?: ViewKey }) => void;
}) {
  const exam = useExamState(scenario);
  const result = computeResult(exam.effective);
  const [singleIndex, setSingleIndex] = useState(0);
  const [sectionIndex, setSectionIndex] = useState(0);

  /* 单题模式：键盘 ←→ 翻题（输入框聚焦时不拦截） */
  useEffect(() => {
    if (view !== "single" || exam.scenario === "grading") return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      if (event.key === "ArrowLeft") setSingleIndex((i) => Math.max(0, i - 1));
      if (event.key === "ArrowRight") setSingleIndex((i) => Math.min(QUESTIONS.length - 1, i + 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, exam.scenario]);

  if (exam.scenario === "grading") {
    return (
      <>
        <GradingScreen />
        <PrototypeReminder />
      </>
    );
  }

  const isResult = exam.scenario === "result";
  const sectionOf = (id: number) => SECTIONS.find((s) => s.ids.includes(id));
  const currentQ = QUESTIONS[singleIndex];
  const currentSection = SECTIONS[sectionIndex];
  const currentSectionAnswered = currentSection.ids.filter((id) => exam.answers[id] !== undefined).length;

  const renderQuestion = (q: MockQuestion, anchorId: string) => (
    <div id={anchorId} className="border-border border-b py-5 last:border-b-0">
      <div className="flex items-start gap-3">
        <span className="text-body font-section text-ink-strong shrink-0 tabular-nums">{q.id}.</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            {q.kind === "fb" ? (
              <p className="text-body text-ink flex-1">&nbsp;</p>
            ) : (
              <p className="text-body text-ink flex-1">{q.stem}</p>
            )}
            {!isResult && exam.answers[q.id] !== undefined && (
              <span className="text-label text-success-foreground shrink-0">已答</span>
            )}
            {isResult && (
              <span className="shrink-0">
                <VerdictTag verdict={verdictOf(q, exam.effective[q.id]).verdict} />
              </span>
            )}
          </div>
          {isResult ? (
            <QuestionReview q={q} answer={exam.effective[q.id]} />
          ) : (
            <QuestionAnswerArea q={q} exam={exam} />
          )}
        </div>
      </div>
    </div>
  );

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex gap-10 py-8">
      {/* 侧栏：作答期=答题卡；结果期=成绩摘要 */}
      <aside className="sticky top-6 w-56 shrink-0 self-start">
        {isResult ? (
          <div>
            <p className="text-label text-muted-foreground">得分</p>
            <p className="text-headline font-headline text-ink-strong mt-1 tabular-nums">
              {result.score100}
              <span className="text-body text-muted-foreground"> / 100</span>
            </p>
            <Separator className="my-4" />
            <div className="space-y-2">
              <p className="text-label text-muted-foreground tabular-nums">答对 {result.correct} · 答错 {result.wrong} · 半对 {result.partial}</p>
              {result.unscored > 0 && (
                <p className="text-label text-muted-foreground tabular-nums">未计分 {result.unscored}（成绩为已计分 {result.counted} 题的平均）</p>
              )}
              {result.review > 0 && (
                <p className="text-label text-warning-foreground tabular-nums">建议人工复核 {result.review} 题</p>
              )}
            </div>
            <Button variant="outline" className="mt-5 w-full cursor-pointer" onClick={exam.restart}>
              再考一张
            </Button>
          </div>
        ) : (
          <div>
            <p className="text-section font-section text-ink">答题卡</p>
            <p className="text-label text-muted-foreground mt-1 tabular-nums">
              已答 {exam.answeredCount} / {QUESTIONS.length} · 已进行 00:32:15
            </p>
            <div className="bg-surface-subtle mt-3 h-1 w-full">
              <div
                className="bg-ink-strong h-full transition-all"
                style={{ width: `${(exam.answeredCount / QUESTIONS.length) * 100}%` }}
              />
            </div>
            <div className="mt-4 grid grid-cols-5 gap-1.5">
              {QUESTIONS.map((q, index) => {
                const answered = exam.answers[q.id] !== undefined;
                const isCurrent = view === "single" && index === singleIndex;
                return (
                  <button
                    key={q.id}
                    type="button"
                    title={`第 ${q.id} 题 · ${TYPE_LABEL[q.kind]}`}
                    aria-label={`跳到第 ${q.id} 题，${TYPE_LABEL[q.kind]}`}
                    className={`text-label h-9 cursor-pointer rounded-xs tabular-nums transition-colors ${
                      isCurrent
                        ? "bg-learning text-primary-foreground"
                        : answered
                          ? "bg-ink-strong text-paper"
                          : "bg-surface-subtle text-muted-foreground hover:bg-surface-strong"
                    }`}
                    onClick={() => {
                      if (view === "single") {
                        setSingleIndex(index);
                        return;
                      }
                      document.getElementById(`proto-q${q.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
                    }}
                  >
                    {q.id}
                  </button>
                );
              })}
            </div>
            <Button
              className="mt-5 w-full cursor-pointer disabled:cursor-not-allowed"
              disabled={!exam.answeredAll}
              onClick={() => exam.setConfirmOpen(true)}
            >
              交卷
            </Button>
            {!exam.answeredAll && (
              <p className="text-label text-muted-foreground mt-2">全部作答后方可交卷</p>
            )}
          </div>
        )}
      </aside>

      {/* 主区 */}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-headline font-headline text-ink-strong">
              {COURSE_NAME} · 第 {EXAM_NO} 次模拟测试
            </h1>
            <p className="text-label text-muted-foreground mt-1.5">
              随机抽题 {QUESTIONS.length} 道 · 单选 6 · 多选 4 · 判断 4 · 填空 3 · 简答 3
            </p>
          </div>
          <Tabs value={view} onValueChange={(v) => onPatch({ view: asView(v) })}>
            <TabsList className="cursor-pointer">
              <TabsTrigger value="single">单题</TabsTrigger>
              <TabsTrigger value="sectioned">分段</TabsTrigger>
              <TabsTrigger value="full">整卷</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {/* 单题形式 */}
        {view === "single" && (
          <div className="mt-6">
            <p className="text-label text-muted-foreground tabular-nums">
              {sectionOf(currentQ.id)?.title} · 第 {singleIndex + 1} / {QUESTIONS.length} 题（键盘 ← → 可翻题）
            </p>
            {/* 进度点行 */}
            <div className="mt-3 flex flex-wrap gap-1.5">
              {QUESTIONS.map((q, index) => (
                <button
                  key={q.id}
                  type="button"
                  title={`第 ${q.id} 题 · ${TYPE_LABEL[q.kind]}`}
                  aria-label={`跳到第 ${q.id} 题`}
                  className={`size-2.5 cursor-pointer rounded-full transition-colors ${
                    index === singleIndex
                      ? "bg-learning"
                      : exam.answers[q.id] !== undefined || isResult
                        ? "bg-ink-strong"
                        : "bg-surface-strong hover:bg-surface-strong/70"
                  }`}
                  onClick={() => setSingleIndex(index)}
                />
              ))}
            </div>
            <div className="border-border mt-4 border-t pt-2">{renderQuestion(currentQ, `proto-q${currentQ.id}`)}</div>
            <div className="mt-5 flex items-center justify-between">
              <Button
                variant="ghost"
                className="cursor-pointer disabled:cursor-not-allowed disabled:opacity-40"
                disabled={singleIndex === 0}
                onClick={() => setSingleIndex((i) => Math.max(0, i - 1))}
              >
                <ChevronLeft className="size-4" /> 上一题
              </Button>
              {singleIndex < QUESTIONS.length - 1 ? (
                <Button variant="outline" className="cursor-pointer" onClick={() => setSingleIndex((i) => i + 1)}>
                  下一题 <ChevronRight className="size-4" />
                </Button>
              ) : isResult ? (
                <Button variant="outline" className="cursor-pointer" onClick={() => setSingleIndex(0)}>
                  回到首题
                </Button>
              ) : (
                <Button
                  className="cursor-pointer disabled:cursor-not-allowed"
                  disabled={!exam.answeredAll}
                  onClick={() => exam.setConfirmOpen(true)}
                >
                  {exam.answeredAll ? "交卷" : "还有题未答"}
                </Button>
              )}
            </div>
          </div>
        )}

        {/* 分段形式 */}
        {view === "sectioned" && (
          <div className="mt-6">
            <div className="flex items-center gap-2">
              {SECTIONS.map((s, index) => {
                const active = index === sectionIndex;
                const secAnswered = s.ids.filter((id) => exam.answers[id] !== undefined).length;
                const done = !isResult && secAnswered === s.ids.length;
                return (
                  <div key={s.key} className="flex flex-1 items-center gap-2 last:flex-none">
                    <button
                      type="button"
                      className={`text-label flex cursor-pointer items-center gap-2 rounded-xs px-2 py-1.5 transition-colors ${
                        active ? "bg-learning-soft text-learning-foreground" : "text-muted-foreground hover:bg-surface-subtle"
                      }`}
                      onClick={() => setSectionIndex(index)}
                    >
                      {done ? (
                        <span className="bg-success-foreground text-paper flex size-4 items-center justify-center rounded-full">
                          <Check className="size-2.5" />
                        </span>
                      ) : (
                        <span className={`size-2.5 rounded-full ${active ? "bg-learning" : "bg-surface-strong"}`} />
                      )}
                      {s.title.replace(/^[一二三四五]、/, "")}
                    </button>
                    {index < SECTIONS.length - 1 && <div className="bg-surface-strong h-px flex-1" />}
                  </div>
                );
              })}
            </div>
            <div className="border-border mt-6 border-t pt-2">
              <div className="flex items-baseline justify-between">
                <h2 className="text-section font-section text-ink">{currentSection.title}</h2>
                {!isResult && (
                  <p className="text-label text-muted-foreground tabular-nums">
                    本段 {currentSectionAnswered} / {currentSection.ids.length}
                  </p>
                )}
              </div>
              <ul className="mt-2">
                {currentSection.ids.map((id) => (
                  <li key={id}>{renderQuestion(qById(id), `proto-q${id}`)}</li>
                ))}
              </ul>
            </div>
            <div className="mt-5 flex items-center justify-between">
              <Button
                variant="ghost"
                className="cursor-pointer disabled:cursor-not-allowed disabled:opacity-40"
                disabled={sectionIndex === 0}
                onClick={() => setSectionIndex((i) => i - 1)}
              >
                上一段
              </Button>
              {sectionIndex < SECTIONS.length - 1 ? (
                <Button variant="outline" className="cursor-pointer" onClick={() => setSectionIndex((i) => i + 1)}>
                  下一段
                </Button>
              ) : (
                !isResult && (
                  <Button
                    className="cursor-pointer disabled:cursor-not-allowed"
                    disabled={!exam.answeredAll}
                    onClick={() => exam.setConfirmOpen(true)}
                  >
                    {exam.answeredAll ? "交卷" : "还有题未答"}
                  </Button>
                )
              )}
            </div>
          </div>
        )}

        {/* 整卷形式 */}
        {view === "full" && (
          <div className="mt-6">
            <div className="border-border border-b pb-6 text-center">
              <p className="text-headline font-headline text-ink-strong">{COURSE_NAME}期末模拟卷</p>
              <p className="text-label text-muted-foreground mt-2 tabular-nums">
                第 {EXAM_NO} 次 · 随机抽题 {QUESTIONS.length} 道 · 满分 100
              </p>
              {isResult && (
                <p className="text-label text-ink mt-3 tabular-nums">
                  得分 <span className="font-section text-ink-strong">{result.score100}</span>
                  {result.unscored > 0 && <span className="text-muted-foreground">（{result.unscored} 题未计分）</span>}
                  {result.review > 0 && <span className="text-warning-foreground"> · {result.review} 题建议人工复核</span>}
                </p>
              )}
            </div>
            {SECTIONS.map((section) => (
              <div key={section.key} className="mt-8">
                <h2 className="text-section font-section text-ink">{section.title}</h2>
                <ul className="mt-2">
                  {section.ids.map((id) => (
                    <li key={id}>{renderQuestion(qById(id), `proto-q${id}`)}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
      <SubmitDialog exam={exam} />
      <PrototypeReminder />
    </section>
  );
}

/** 试卷底部的原型水印（防止演示数据被误认为真实功能） */
function PrototypeReminder() {
  return (
    <p className="text-label text-muted-foreground/70 mt-8 text-center">
      PROTOTYPE · 演示数据 · 底部浮条可切换场景
    </p>
  );
}
