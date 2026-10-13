import {
  Archive,
  ArchiveRestore,
  ArrowLeftRight,
  BookmarkPlus,
  Brain,
  CalendarCheck2,
  CalendarClock,
  CalendarPlus,
  CheckCheck,
  ClipboardCheck,
  Clock,
  FileX,
  FileSearch,
  History,
  Flag,
  FolderArchive,
  FolderInput,
  FolderPen,
  FolderPlus,
  Globe,
  Goal,
  GraduationCap,
  Layers,
  Library,
  Link2,
  Link2Off,
  ListTodo,
  MessageSquareText,
  NotebookPen,
  PencilLine,
  RefreshCw,
  RotateCcw,
  Rows3,
  Search,
  Share2,
  SquarePen,
  Target,
  Timer,
  Trash2,
  Undo2,
  WandSparkles,
  Wrench,
} from "lucide-react";

/**
 * 工具图标：一个工具一个图标，行内文案之外用以区分不同工具。
 * 含已退出模型工具面的 search_transcript（历史过程条目仍可能引用）；
 * 后端新增工具未登记时落 TOOL_ICON_FALLBACK。
 */
export const TOOL_ICONS: Record<string, typeof Wrench> = {
  // 检索
  search_library: Library,
  search_courses: GraduationCap,
  search_transcript: Search,
  search_context: History,
  read_context: FileSearch,
  web_search: Globe,
  // 列表与查询
  list_course_records: Rows3,
  list_library_items: Layers,
  list_goals: Target,
  get_goal: Goal,
  get_plan: CalendarCheck2,
  list_shared_refs: Share2,
  // 时间
  get_current_time: Clock,
  convert_time: ArrowLeftRight,
  shift_datetime: CalendarPlus,
  diff_datetime: Timer,
  // 计划与目标
  generate_learning_plan: WandSparkles,
  confirm_plan: ClipboardCheck,
  update_plan_item: CalendarClock,
  complete_plan_item: CheckCheck,
  regenerate_plan: RefreshCw,
  create_goal: Flag,
  update_goal: SquarePen,
  // 课程与资料
  create_course: FolderPlus,
  update_course: FolderPen,
  archive_course: FolderArchive,
  restore_course: ArchiveRestore,
  delete_course: Trash2,
  move_record_course: FolderInput,
  add_text_record_to_course: NotebookPen,
  update_library_item: PencilLine,
  archive_library_item: Archive,
  restore_library_item: RotateCcw,
  soft_delete_record: FileX,
  add_shared_ref: Link2,
  remove_shared_ref: Link2Off,
  // 记忆、研究与撤销
  propose_memory: Brain,
  propose_ingest: BookmarkPlus,
  plan_batch_operations: ListTodo,
  undo_operation: Undo2,
};

export const TOOL_ICON_FALLBACK = Wrench;

/** 公开说明（思考）行图标，与工具行区分。 */
export const COMMENTARY_ICON = MessageSquareText;
