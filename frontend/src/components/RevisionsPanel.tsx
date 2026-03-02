import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, RotateCcw } from "lucide-react";

import { api } from "../lib/api";
import { computeDiff, type DiffSummary } from "../lib/diffBlocks";
import type { Entry } from "../lib/types";

export type Revision = {
  id: number;
  entry_id: string;
  author_id: string;
  content_blocks: Array<Record<string, unknown>>;
  change_summary: string;
  created_at: string;
};

type RevisionRow = Revision & { diff: DiffSummary; afterContent: Array<Record<string, unknown>> };

export function RevisionsPanel({
  entry,
  onRestore,
  onPreview,
  activePreviewId,
}: {
  entry: Entry | null;
  onRestore?: () => void;
  onPreview?: (revision: Revision | null) => void;
  activePreviewId?: number | null;
}) {
  const queryClient = useQueryClient();

  const revisionsQuery = useQuery({
    queryKey: ["revisions", entry?.id],
    queryFn: async () => {
      const { data } = await api.get<Revision[]>(`/entries/${entry!.id}/revisions`);
      return data;
    },
    enabled: !!entry,
  });

  const restore = useMutation({
    mutationFn: async ({ entryId, revisionId }: { entryId: string; revisionId: number }) => {
      await api.post(`/entries/${entryId}/revisions/${revisionId}/restore`);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["entries"] });
      await queryClient.invalidateQueries({ queryKey: ["revisions"] });
      onRestore?.();
    },
  });

  const revisions = revisionsQuery.data ?? [];

  // Revisions are ordered newest-first.
  // revision[i].content_blocks = state *before* that update.
  // "after" for revision[i] is revision[i-1].content_blocks, except for
  // i===0 where "after" is the current entry content.
  const rows: RevisionRow[] = useMemo(() => {
    if (!entry || revisions.length === 0) return [];
    return revisions.map((rev, i) => {
      const before = rev.content_blocks;
      const after =
        i === 0
          ? (entry.content_blocks as Record<string, unknown>[])
          : revisions[i - 1].content_blocks;
      return { ...rev, diff: computeDiff(before, after), afterContent: after };
    });
  }, [entry, revisions]);

  if (!entry) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-slate-500 dark:text-slate-400">
        Select an entry to view history.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col text-sm">
      <div className="flex shrink-0 items-center gap-1.5 border-b border-slate-200 dark:border-slate-800 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
        <History size={12} />
        <span>Revisions</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {revisionsQuery.isLoading && (
          <div className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">Loading…</div>
        )}

        {!revisionsQuery.isLoading && rows.length === 0 && (
          <div className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
            No revisions yet.
          </div>
        )}

        {rows.map((rev, i) => {
          const isActive = activePreviewId === rev.id;
          const isNewest = i === 0;
          return (
          <div
            key={rev.id}
            className={`group cursor-pointer border-b border-slate-100 dark:border-slate-800 px-3 py-1.5 ${
              isActive
                ? "bg-blue-50 dark:bg-blue-900/30"
                : "hover:bg-slate-50 dark:hover:bg-slate-800/60"
            }`}
            onClick={() => onPreview?.(isActive || isNewest ? null : { ...rev, content_blocks: rev.afterContent })}
          >
            <div className="flex items-center justify-between">
              <div className="text-[11px] text-slate-500 dark:text-slate-400">
                {new Date(rev.created_at).toLocaleString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </div>
              <button
                title="Restore this revision"
                className="opacity-0 p-0.5 text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 group-hover:opacity-100"
                onClick={(e) => {
                  e.stopPropagation();
                  restore.mutate({ entryId: entry.id, revisionId: rev.id });
                }}
              >
                <RotateCcw size={12} />
              </button>
            </div>

            <div className="mt-0.5 flex items-center gap-2 text-xs">
              {rev.diff.added > 0 && (
                <span className="font-mono text-green-600 dark:text-green-400">
                  +{rev.diff.added}
                </span>
              )}
              {rev.diff.removed > 0 && (
                <span className="font-mono text-red-600 dark:text-red-400">
                  −{rev.diff.removed}
                </span>
              )}
              {rev.diff.added === 0 && rev.diff.removed === 0 && (
                <span className="text-slate-400 dark:text-slate-500">no block changes</span>
              )}
            </div>

            {rev.diff.headingContext && (
              <div className="mt-0.5 truncate text-[11px] text-slate-600 dark:text-slate-300">
                {rev.diff.headingAction === "added" ? "+ §" : "− §"} {rev.diff.headingContext}
              </div>
            )}
          </div>
          );
        })}
      </div>
    </div>
  );
}
