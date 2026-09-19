import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Sparkles, Wand2, X } from "lucide-react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import {
  libraryApi,
  type AgentProposalOut,
} from "@/features/library/api/library";
import { libraryKeys } from "@/features/library/api/keys";
import { ApiError } from "@/services/http/client";

type DecisionMutation = UseMutationResult<
  AgentProposalOut,
  Error,
  { proposalId: string; accept: boolean }
>;

/**
 * 「AI 整理」对话框（工单 05）：确定性检测结果（重复/失败，零 LLM） +
 * LLM 标题与归类建议（ORGANIZE 提案）+ 待审提案逐项确认/拒绝。
 * 拒绝不改事实；确认由后端领域 Service 原子应用。
 */
export function OrganizeDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [proposeError, setProposeError] = useState<string | null>(null);

  const scanQuery = useQuery({
    queryKey: libraryKeys.organizeScan(),
    queryFn: () => libraryApi.organizeScan(),
    enabled: open,
  });

  const propose = useMutation({
    mutationFn: () => libraryApi.organizePropose(),
    onSuccess: (result) => {
      setProposeError(
        result.created.length === 0
          ? t("library.organize.noSuggestions")
          : null,
      );
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
    },
    onError: (error) => {
      setProposeError(
        error instanceof ApiError ? error.message : t("library.organize.error"),
      );
    },
  });

  const decision = useMutation({
    mutationFn: ({
      proposalId,
      accept,
    }: {
      proposalId: string;
      accept: boolean;
    }) =>
      accept
        ? libraryApi.confirmProposal(proposalId)
        : libraryApi.rejectProposal(proposalId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
    },
  });

  const duplicates = scanQuery.data?.duplicates ?? [];
  const failedItems = scanQuery.data?.failed_items ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("library.organize.title")}</DialogTitle>
          <DialogDescription>
            {t("library.organize.description")}
          </DialogDescription>
        </DialogHeader>

        <section aria-label={t("library.organize.deterministic")}>
          <h4 className="text-label text-muted-foreground font-label mb-2">
            {t("library.organize.deterministic")}
          </h4>
          {scanQuery.isPending ? (
            <div className="text-muted-foreground flex items-center gap-2 text-sm">
              <Spinner className="size-4" />
            </div>
          ) : scanQuery.isError ? (
            <p role="alert" className="text-destructive text-sm">
              {t("library.organize.scanError")}
            </p>
          ) : duplicates.length === 0 && failedItems.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              {t("library.organize.noIssues")}
            </p>
          ) : (
            <div className="space-y-2">
              {duplicates.length > 0 ? (
                <Alert>
                  <AlertDescription>
                    <p className="mb-1 font-medium">
                      {t("library.organize.duplicatesTitle", {
                        count: duplicates.length,
                      })}
                    </p>
                    <ul className="list-disc space-y-1 pl-4">
                      {duplicates.map((group) => (
                        <li key={group.content_hash}>
                          {group.items.map((item) => item.title).join(" / ")}
                        </li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              ) : null}
              {failedItems.length > 0 ? (
                <Alert variant="destructive">
                  <AlertDescription>
                    <p className="mb-1 font-medium">
                      {t("library.organize.failedTitle", {
                        count: failedItems.length,
                      })}
                    </p>
                    <ul className="list-disc pl-4">
                      {failedItems.map((item) => (
                        <li key={item.id} className="truncate">
                          {item.title}
                        </li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              ) : null}
            </div>
          )}
          {(scanQuery.data?.unclassified.length ?? 0) > 0 ? (
            <p className="text-muted-foreground text-label mt-2">
              {t("library.organize.unclassifiedCount", {
                count: scanQuery.data?.unclassified.length ?? 0,
              })}
            </p>
          ) : null}
        </section>

        <section aria-label={t("library.organize.aiSection")}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h4 className="text-label text-muted-foreground font-label">
              {t("library.organize.aiSection")}
            </h4>
            <Button
              size="sm"
              variant="outline"
              onClick={() => propose.mutate()}
              disabled={propose.isPending}
            >
              {propose.isPending ? (
                <Spinner className="size-4" aria-hidden />
              ) : (
                <Wand2 className="size-4" aria-hidden />
              )}
              {t("library.organize.generate")}
            </Button>
          </div>
          {proposeError ? (
            <p role="alert" className="text-destructive text-label mb-2">
              {proposeError}
            </p>
          ) : null}
          <PendingProposals decision={decision} />
        </section>
      </DialogContent>
    </Dialog>
  );
}

function PendingProposals({ decision }: { decision: DecisionMutation }) {
  const { t } = useTranslation();
  const proposals = useQuery({
    queryKey: libraryKeys.proposals("PENDING"),
    queryFn: () => libraryApi.listProposals({ status: "PENDING" }),
  });
  const rows = proposals.data ?? [];
  if (rows.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        {t("library.organize.noProposals")}
      </p>
    );
  }
  return (
    <ul className="space-y-1" aria-label={t("library.organize.pendingList")}>
      {rows.map((proposal) => (
        <ProposalRow
          key={proposal.id}
          proposal={proposal}
          decision={decision}
        />
      ))}
    </ul>
  );
}

function ProposalRow({
  proposal,
  decision,
}: {
  proposal: AgentProposalOut;
  decision: DecisionMutation;
}) {
  const { t } = useTranslation();
  const payload = proposal.payload as {
    item_id?: string;
    title?: string;
    course_id?: string;
    url?: string;
  };
  const busy =
    decision.isPending && decision.variables?.proposalId === proposal.id;
  return (
    <li className="bg-surface-subtle flex items-center gap-2 rounded-lg px-3 py-2">
      <Sparkles className="text-muted-foreground size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-label truncate">
          {proposal.proposal_type === "RESEARCH_INGEST"
            ? t("library.organize.researchIngest", {
                title: payload.title ?? payload.url ?? "",
              })
            : t("library.organize.organizeSuggestion", {
                title: payload.title ?? payload.item_id ?? "",
              })}
        </p>
        <p className="text-muted-foreground text-label truncate">
          {payload.course_id
            ? t("library.organize.withCourse")
            : t("library.organize.titleOnly")}
        </p>
      </div>
      <Button
        size="icon-sm"
        variant="ghost"
        aria-label={t("library.organize.accept")}
        disabled={busy}
        onClick={() =>
          decision.mutate({ proposalId: proposal.id, accept: true })
        }
      >
        <Check className="size-4" aria-hidden />
      </Button>
      <Button
        size="icon-sm"
        variant="ghost"
        aria-label={t("library.organize.reject")}
        disabled={busy}
        onClick={() =>
          decision.mutate({ proposalId: proposal.id, accept: false })
        }
      >
        <X className="size-4" aria-hidden />
      </Button>
    </li>
  );
}
