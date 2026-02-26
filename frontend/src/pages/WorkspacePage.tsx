import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  FilePlus2,
  FileText,
  Folder,
  FolderPlus,
  MoveRight,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";

import { EntryEditorForm } from "../components/EntryEditorForm";
import { api } from "../lib/api";
import type { Entry, Notebook } from "../lib/types";

type ContextMenuState =
  | {
      x: number;
      y: number;
      kind: "root";
    }
  | {
      x: number;
      y: number;
      kind: "notebook";
      notebookId: string;
    }
  | {
      x: number;
      y: number;
      kind: "entry";
      entryId: string;
      notebookId: string;
    };

type RenameState =
  | { kind: "notebook"; id: string; value: string }
  | { kind: "entry"; id: string; value: string }
  | null;

export function WorkspacePage() {
  const queryClient = useQueryClient();
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [expandedNotebookIds, setExpandedNotebookIds] = useState<Record<string, boolean>>({});
  const [creatingNotebookName, setCreatingNotebookName] = useState("");
  const [creatingEntryNotebookId, setCreatingEntryNotebookId] = useState<string | null>(null);
  const [creatingEntryTitle, setCreatingEntryTitle] = useState("");
  const [renameState, setRenameState] = useState<RenameState>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [movingEntryId, setMovingEntryId] = useState<string | null>(null);
  const [moveTargetNotebookId, setMoveTargetNotebookId] = useState<string>("");

  const [leftPaneWidth, setLeftPaneWidth] = useState(320);
  const [rightPaneWidth, setRightPaneWidth] = useState(280);
  const dragState = useRef<{ side: "left" | "right"; startX: number; startWidth: number } | null>(null);

  useEffect(() => {
    const onMouseMove = (event: MouseEvent) => {
      if (!dragState.current) return;
      if (dragState.current.side === "left") {
        const next = dragState.current.startWidth + (event.clientX - dragState.current.startX);
        setLeftPaneWidth(Math.max(220, Math.min(520, next)));
      } else {
        const next = dragState.current.startWidth - (event.clientX - dragState.current.startX);
        setRightPaneWidth(Math.max(220, Math.min(520, next)));
      }
    };

    const onMouseUp = () => {
      dragState.current = null;
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  const notebooksQuery = useQuery({
    queryKey: ["notebooks"],
    queryFn: async () => {
      const { data } = await api.get<Notebook[]>("/notebooks/");
      return data;
    },
  });

  const entriesQueries = useQueries({
    queries: (notebooksQuery.data ?? []).map((notebook) => ({
      queryKey: ["entries", "notebook", notebook.id],
      queryFn: async () => {
        const { data } = await api.get<Entry[]>(`/entries/notebook/${notebook.id}`);
        return data;
      },
      enabled: Boolean(notebooksQuery.data),
    })),
  });

  const entriesByNotebook = useMemo(() => {
    const result: Record<string, Entry[]> = {};
    (notebooksQuery.data ?? []).forEach((notebook, idx) => {
      result[notebook.id] = entriesQueries[idx]?.data ?? [];
    });
    return result;
  }, [notebooksQuery.data, entriesQueries]);

  const allEntries = useMemo(() => Object.values(entriesByNotebook).flat(), [entriesByNotebook]);

  const selectedEntry = useMemo(() => {
    return allEntries.find((entry) => entry.id === selectedEntryId) ?? allEntries[0] ?? null;
  }, [allEntries, selectedEntryId]);

  const refreshTree = async () => {
    await queryClient.invalidateQueries({ queryKey: ["notebooks"] });
    await queryClient.invalidateQueries({ queryKey: ["entries"] });
  };

  const createNotebook = useMutation({
    mutationFn: async (title: string) => {
      const { data } = await api.post<Notebook>("/notebooks/", { title, description: "" });
      return data;
    },
    onSuccess: async (notebook) => {
      await refreshTree();
      setExpandedNotebookIds((prev) => ({ ...prev, [notebook.id]: true }));
    },
  });

  const renameNotebook = useMutation({
    mutationFn: async ({ notebookId, title }: { notebookId: string; title: string }) => {
      await api.patch(`/notebooks/${notebookId}`, { title });
    },
    onSuccess: refreshTree,
  });

  const deleteNotebook = useMutation({
    mutationFn: async (notebookId: string) => {
      await api.delete(`/notebooks/${notebookId}`);
    },
    onSuccess: refreshTree,
  });

  const createEntry = useMutation({
    mutationFn: async ({ notebookId, title }: { notebookId: string; title: string }) => {
      const { data } = await api.post<Entry>("/entries/", {
        notebook_id: notebookId,
        title,
        content_blocks: [],
        tags: [],
      });
      return data;
    },
    onSuccess: async (entry) => {
      await refreshTree();
      setSelectedEntryId(entry.id);
      setExpandedNotebookIds((prev) => ({ ...prev, [entry.notebook_id]: true }));
    },
  });

  const renameEntry = useMutation({
    mutationFn: async ({ entryId, title }: { entryId: string; title: string }) => {
      await api.put(`/entries/${entryId}`, {
        title,
        change_summary: "Renamed in tree",
      });
    },
    onSuccess: refreshTree,
  });

  const moveEntry = useMutation({
    mutationFn: async ({ entryId, notebookId }: { entryId: string; notebookId: string }) => {
      await api.put(`/entries/${entryId}`, {
        notebook_id: notebookId,
        change_summary: "Moved in tree",
      });
    },
    onSuccess: async () => {
      await refreshTree();
      setMovingEntryId(null);
      setMoveTargetNotebookId("");
    },
  });

  const deleteEntry = useMutation({
    mutationFn: async (entryId: string) => {
      await api.delete(`/entries/${entryId}`);
    },
    onSuccess: refreshTree,
  });

  const saveEntry = useMutation({
    mutationFn: async (payload: {
      id: string;
      title: string;
      content_blocks: Array<Record<string, unknown>>;
    }) => {
      await api.put(`/entries/${payload.id}`, {
        title: payload.title,
        content_blocks: payload.content_blocks,
        change_summary: "Edited in workspace",
      });
    },
    onSuccess: refreshTree,
  });

  const orderedNotebooks = notebooksQuery.data ?? [];

  const submitCreateNotebook = async () => {
    const title = creatingNotebookName.trim();
    if (!title) return;
    await createNotebook.mutateAsync(title);
    setCreatingNotebookName("");
  };

  const submitCreateEntry = async () => {
    if (!creatingEntryNotebookId) return;
    const title = creatingEntryTitle.trim();
    if (!title) return;
    await createEntry.mutateAsync({ notebookId: creatingEntryNotebookId, title });
    setCreatingEntryNotebookId(null);
    setCreatingEntryTitle("");
  };

  const submitRename = async () => {
    if (!renameState) return;
    const value = renameState.value.trim();
    if (!value) return;
    if (renameState.kind === "notebook") {
      await renameNotebook.mutateAsync({ notebookId: renameState.id, title: value });
    } else {
      await renameEntry.mutateAsync({ entryId: renameState.id, title: value });
    }
    setRenameState(null);
  };

  const openContextMenu = (event: ReactMouseEvent, state: ContextMenuState) => {
    event.preventDefault();
    setContextMenu(state);
  };

  const menuEntry = contextMenu?.kind === "entry" ? allEntries.find((e) => e.id === contextMenu.entryId) : null;

  return (
    <div
      className="grid h-[calc(100vh-72px)] bg-white"
      style={{ gridTemplateColumns: `${leftPaneWidth}px 1px minmax(0,1fr) 1px ${rightPaneWidth}px` }}
      onClick={() => setContextMenu(null)}
      onContextMenu={(event) => {
        if (event.target === event.currentTarget) {
          openContextMenu(event, { x: event.clientX, y: event.clientY, kind: "root" });
        }
      }}
    >
      <aside className="overflow-y-auto border-r border-slate-200 text-sm">
        <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-600">
          <span>Explorer</span>
          <div className="flex items-center gap-1">
            <button
              title="New Notebook"
              className="p-1 hover:bg-slate-100"
              onClick={() => {
                setCreatingNotebookName("Untitled Notebook");
                setCreatingEntryNotebookId(null);
                setRenameState(null);
              }}
            >
              <FolderPlus size={14} />
            </button>
            <button
              title="New Entry"
              className="p-1 hover:bg-slate-100"
              onClick={() => {
                const firstNotebook = orderedNotebooks[0];
                if (!firstNotebook) return;
                setCreatingEntryNotebookId(firstNotebook.id);
                setCreatingEntryTitle("Untitled Entry");
                setExpandedNotebookIds((prev) => ({ ...prev, [firstNotebook.id]: true }));
                setRenameState(null);
              }}
            >
              <FilePlus2 size={14} />
            </button>
          </div>
        </div>

        <div className="py-1">
          {creatingNotebookName !== "" && (
            <div className="flex items-center gap-2 px-3 py-1">
              <Folder size={14} className="text-slate-500" />
              <input
                autoFocus
                value={creatingNotebookName}
                onChange={(event) => setCreatingNotebookName(event.target.value)}
                onBlur={submitCreateNotebook}
                onKeyDown={async (event) => {
                  if (event.key === "Enter") await submitCreateNotebook();
                  if (event.key === "Escape") setCreatingNotebookName("");
                }}
                className="w-full border border-slate-300 px-1 py-0.5 text-sm outline-none"
              />
            </div>
          )}

          {notebooksQuery.isLoading && <div className="px-3 py-2 text-slate-500">Loading...</div>}

          {orderedNotebooks.map((notebook) => {
            const entries = entriesByNotebook[notebook.id] ?? [];
            const expanded = expandedNotebookIds[notebook.id] ?? true;

            return (
              <div key={notebook.id}>
                <div
                  className="group flex items-center gap-1 px-2 py-1 hover:bg-slate-100"
                  onContextMenu={(event) =>
                    openContextMenu(event, {
                      x: event.clientX,
                      y: event.clientY,
                      kind: "notebook",
                      notebookId: notebook.id,
                    })
                  }
                >
                  <button
                    className="p-0.5"
                    onClick={() =>
                      setExpandedNotebookIds((prev) => ({
                        ...prev,
                        [notebook.id]: !(prev[notebook.id] ?? true),
                      }))
                    }
                  >
                    {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>
                  <Folder size={14} className="text-slate-500" />

                  {renameState?.kind === "notebook" && renameState.id === notebook.id ? (
                    <input
                      autoFocus
                      value={renameState.value}
                      onChange={(event) =>
                        setRenameState({ kind: "notebook", id: notebook.id, value: event.target.value })
                      }
                      onBlur={submitRename}
                      onKeyDown={async (event) => {
                        if (event.key === "Enter") await submitRename();
                        if (event.key === "Escape") setRenameState(null);
                      }}
                      className="w-full border border-slate-300 px-1 py-0.5 text-sm outline-none"
                    />
                  ) : (
                    <button
                      className="truncate text-left"
                      onClick={() => {
                        setExpandedNotebookIds((prev) => ({ ...prev, [notebook.id]: true }));
                        if (entries[0]) setSelectedEntryId(entries[0].id);
                      }}
                    >
                      {notebook.title}
                    </button>
                  )}

                  <button
                    className="ml-auto hidden p-1 text-slate-500 hover:bg-slate-200 group-hover:block"
                    title="New Entry"
                    onClick={() => {
                      setCreatingEntryNotebookId(notebook.id);
                      setCreatingEntryTitle("Untitled Entry");
                      setExpandedNotebookIds((prev) => ({ ...prev, [notebook.id]: true }));
                    }}
                  >
                    <Plus size={12} />
                  </button>
                </div>

                {expanded && (
                  <div className="pl-7">
                    {creatingEntryNotebookId === notebook.id && (
                      <div className="flex items-center gap-2 py-1 pr-2">
                        <FileText size={14} className="text-slate-500" />
                        <input
                          autoFocus
                          value={creatingEntryTitle}
                          onChange={(event) => setCreatingEntryTitle(event.target.value)}
                          onBlur={submitCreateEntry}
                          onKeyDown={async (event) => {
                            if (event.key === "Enter") await submitCreateEntry();
                            if (event.key === "Escape") {
                              setCreatingEntryNotebookId(null);
                              setCreatingEntryTitle("");
                            }
                          }}
                          className="w-full border border-slate-300 px-1 py-0.5 text-sm outline-none"
                        />
                      </div>
                    )}

                    {entries.map((entry) => (
                      <div
                        key={entry.id}
                        className={`group flex items-center gap-2 py-1 pr-2 ${
                          selectedEntry?.id === entry.id ? "bg-blue-100" : "hover:bg-slate-100"
                        }`}
                        onContextMenu={(event) =>
                          openContextMenu(event, {
                            x: event.clientX,
                            y: event.clientY,
                            kind: "entry",
                            entryId: entry.id,
                            notebookId: notebook.id,
                          })
                        }
                      >
                        <FileText size={14} className="text-slate-500" />

                        {renameState?.kind === "entry" && renameState.id === entry.id ? (
                          <input
                            autoFocus
                            value={renameState.value}
                            onChange={(event) =>
                              setRenameState({ kind: "entry", id: entry.id, value: event.target.value })
                            }
                            onBlur={submitRename}
                            onKeyDown={async (event) => {
                              if (event.key === "Enter") await submitRename();
                              if (event.key === "Escape") setRenameState(null);
                            }}
                            className="w-full border border-slate-300 px-1 py-0.5 text-sm outline-none"
                          />
                        ) : (
                          <button className="truncate text-left" onClick={() => setSelectedEntryId(entry.id)}>
                            {entry.title}
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {movingEntryId && (
          <div className="border-t border-slate-200 px-3 py-2">
            <div className="mb-1 text-xs text-slate-600">Move entry to notebook</div>
            <select
              value={moveTargetNotebookId}
              onChange={(event) => setMoveTargetNotebookId(event.target.value)}
              className="mb-2 w-full border border-slate-300 bg-white px-2 py-1 text-sm"
            >
              <option value="">Select notebook...</option>
              {orderedNotebooks.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.title}
                </option>
              ))}
            </select>
            <div className="flex gap-2">
              <button
                className="border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
                onClick={async () => {
                  if (!moveTargetNotebookId) return;
                  await moveEntry.mutateAsync({ entryId: movingEntryId, notebookId: moveTargetNotebookId });
                }}
              >
                Move
              </button>
              <button
                className="border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
                onClick={() => {
                  setMovingEntryId(null);
                  setMoveTargetNotebookId("");
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </aside>

      <div
        className="cursor-col-resize bg-slate-300 hover:bg-slate-400"
        onMouseDown={(event) => {
          dragState.current = { side: "left", startX: event.clientX, startWidth: leftPaneWidth };
        }}
      />

      <section className="overflow-y-auto bg-white">
        {selectedEntry ? (
          <EntryEditorForm
            initialTitle={selectedEntry.title}
            initialContent={selectedEntry.content_blocks}
            isSaving={saveEntry.isPending}
            onSave={async (payload) => {
              await saveEntry.mutateAsync({
                id: selectedEntry.id,
                title: payload.title,
                content_blocks: payload.content_blocks,
              });
            }}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            Create an entry from Explorer to begin.
          </div>
        )}
      </section>

      <div
        className="cursor-col-resize bg-slate-300 hover:bg-slate-400"
        onMouseDown={(event) => {
          dragState.current = { side: "right", startX: event.clientX, startWidth: rightPaneWidth };
        }}
      />

      <aside className="border-l border-slate-200 bg-white p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-600">Inspector</div>
        <p className="mt-2 text-sm text-slate-500">Reserved for future tools.</p>
      </aside>

      {contextMenu && (
        <div
          className="fixed z-50 min-w-44 border border-slate-300 bg-white py-1 text-sm shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          {contextMenu.kind === "root" && (
            <button
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100"
              onClick={() => {
                setContextMenu(null);
                setCreatingNotebookName("Untitled Notebook");
                setRenameState(null);
              }}
            >
              <FolderPlus size={14} /> New Notebook
            </button>
          )}

          {contextMenu.kind === "notebook" && (
            <>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100"
                onClick={() => {
                  setContextMenu(null);
                  setCreatingEntryNotebookId(contextMenu.notebookId);
                  setCreatingEntryTitle("Untitled Entry");
                  setExpandedNotebookIds((prev) => ({ ...prev, [contextMenu.notebookId]: true }));
                }}
              >
                <FilePlus2 size={14} /> New Entry
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100"
                onClick={() => {
                  const notebook = orderedNotebooks.find((n) => n.id === contextMenu.notebookId);
                  setContextMenu(null);
                  setRenameState({ kind: "notebook", id: contextMenu.notebookId, value: notebook?.title ?? "" });
                }}
              >
                <Pencil size={14} /> Rename
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-red-700 hover:bg-red-50"
                onClick={async () => {
                  setContextMenu(null);
                  await deleteNotebook.mutateAsync(contextMenu.notebookId);
                }}
              >
                <Trash2 size={14} /> Delete
              </button>
            </>
          )}

          {contextMenu.kind === "entry" && (
            <>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100"
                onClick={() => {
                  setContextMenu(null);
                  setRenameState({ kind: "entry", id: contextMenu.entryId, value: menuEntry?.title ?? "" });
                }}
              >
                <Pencil size={14} /> Rename
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100"
                onClick={() => {
                  setContextMenu(null);
                  setMovingEntryId(contextMenu.entryId);
                  setMoveTargetNotebookId("");
                }}
              >
                <MoveRight size={14} /> Move...
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-red-700 hover:bg-red-50"
                onClick={async () => {
                  setContextMenu(null);
                  await deleteEntry.mutateAsync(contextMenu.entryId);
                }}
              >
                <Trash2 size={14} /> Delete
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
