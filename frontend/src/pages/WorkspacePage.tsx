import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  Download,
  FilePlus2,
  FileText,
  Folder,
  FolderPlus,
  Paperclip,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";

import { EntryEditorForm, type AttachmentDropData } from "../components/EntryEditorForm";
import { RevisionsPanel, type Revision } from "../components/RevisionsPanel";
import { api } from "../lib/api";
import type { Attachment, Entry, Notebook } from "../lib/types";

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
    }
  | {
      x: number;
      y: number;
      kind: "attachment";
      attachmentId: string;
      filename: string;
    };

type RenameState =
  | { kind: "notebook"; id: string; value: string }
  | { kind: "entry"; id: string; value: string }
  | null;

export function WorkspacePage() {
  const queryClient = useQueryClient();
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [editorGeneration, setEditorGeneration] = useState(0);
  const [previewRevision, setPreviewRevision] = useState<Revision | null>(null);
  const [expandedNotebookIds, setExpandedNotebookIds] = useState<Record<string, boolean>>({});
  const [creatingNotebookName, setCreatingNotebookName] = useState("");
  const [creatingEntryNotebookId, setCreatingEntryNotebookId] = useState<string | null>(null);
  const [creatingEntryTitle, setCreatingEntryTitle] = useState("");
  const [renameState, setRenameState] = useState<RenameState>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [draggingEntry, setDraggingEntry] = useState<{ entryId: string; fromNotebookId: string } | null>(null);
  const [dropNotebookId, setDropNotebookId] = useState<string | null>(null);
  const [fileDropNotebookId, setFileDropNotebookId] = useState<string | null>(null);
  const [fileDropEntryId, setFileDropEntryId] = useState<string | null>(null);
  const [draggingAttachment, setDraggingAttachment] = useState<{ attachmentId: string; fromEntryId: string } | null>(null);
  const [attDropEntryId, setAttDropEntryId] = useState<string | null>(null);

  const [leftPaneWidth, setLeftPaneWidth] = useState(320);
  const [rightPaneWidth, setRightPaneWidth] = useState(280);
  const [revisionsPaneHeight, setRevisionsPaneHeight] = useState(200);
  const dragState = useRef<{
    side: "left" | "right" | "revisions";
    startX: number;
    startY: number;
    startWidth: number;
    startHeight: number;
  } | null>(null);

  useEffect(() => {
    const onMouseMove = (event: MouseEvent) => {
      if (!dragState.current) return;
      if (dragState.current.side === "left") {
        const next = dragState.current.startWidth + (event.clientX - dragState.current.startX);
        setLeftPaneWidth(Math.max(220, Math.min(520, next)));
      } else if (dragState.current.side === "right") {
        const next = dragState.current.startWidth - (event.clientX - dragState.current.startX);
        setRightPaneWidth(Math.max(220, Math.min(520, next)));
      } else {
        const next = dragState.current.startHeight - (event.clientY - dragState.current.startY);
        setRevisionsPaneHeight(Math.max(80, Math.min(500, next)));
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

  const attachmentsQueries = useQueries({
    queries: allEntries.map((entry) => ({
      queryKey: ["attachments", "entry", entry.id],
      queryFn: async () => {
        const { data } = await api.get<Attachment[]>(`/attachments/entry/${entry.id}`);
        return data;
      },
    })),
  });

  const attachmentsByEntry = useMemo(() => {
    const result: Record<string, Attachment[]> = {};
    allEntries.forEach((entry, idx) => {
      result[entry.id] = attachmentsQueries[idx]?.data ?? [];
    });
    return result;
  }, [allEntries, attachmentsQueries]);

  const selectedEntry = useMemo(() => {
    return allEntries.find((entry) => entry.id === selectedEntryId) ?? allEntries[0] ?? null;
  }, [allEntries, selectedEntryId]);

  // Clear revision preview when switching entries.
  const prevEntryIdRef = useRef(selectedEntryId);
  useEffect(() => {
    if (prevEntryIdRef.current !== selectedEntryId) {
      setPreviewRevision(null);
      prevEntryIdRef.current = selectedEntryId;
    }
  }, [selectedEntryId]);

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
      });
    },
    onSuccess: refreshTree,
  });

  const moveEntry = useMutation({
    mutationFn: async ({ entryId, notebookId }: { entryId: string; notebookId: string }) => {
      await api.put(`/entries/${entryId}`, {
        notebook_id: notebookId,
      });
    },
    onSuccess: async () => {
      await refreshTree();
      setDropNotebookId(null);
    },
  });

  const importMarkdown = useMutation({
    mutationFn: async ({ notebookId, filename, markdown }: { notebookId: string; filename: string; markdown: string }) => {
      const { data } = await api.post<Entry>("/entries/import", {
        notebook_id: notebookId,
        filename,
        markdown,
      });
      return data;
    },
    onSuccess: async (entry) => {
      await refreshTree();
      setSelectedEntryId(entry.id);
      setExpandedNotebookIds((prev) => ({ ...prev, [entry.notebook_id]: true }));
    },
  });

  const uploadAttachment = useMutation({
    mutationFn: async ({ entryId, file }: { entryId: string; file: File }) => {
      const form = new FormData();
      form.append("entry_id", entryId);
      form.append("file", file);
      const { data } = await api.post("/attachments/", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["attachments"] });
    },
  });

  const moveAttachment = useMutation({
    mutationFn: async ({ attachmentId, entryId }: { attachmentId: string; entryId: string }) => {
      await api.patch(`/attachments/${attachmentId}`, { entry_id: entryId });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["attachments"] });
    },
  });

  const deleteAttachment = useMutation({
    mutationFn: async (attachmentId: string) => {
      await api.delete(`/attachments/${attachmentId}`);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["attachments"] });
    },
  });

  const downloadAttachment = async (attachmentId: string, filename: string) => {
    const resp = await api.get(`/attachments/${attachmentId}`, { responseType: "blob" });
    const url = URL.createObjectURL(resp.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

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
      checkpoint: boolean;
    }) => {
      await api.put(`/entries/${payload.id}`, {
        title: payload.title,
        content_blocks: payload.content_blocks,
        checkpoint: payload.checkpoint,
        change_summary: payload.checkpoint ? "Saved in workspace" : "",
      });
      return payload.checkpoint;
    },
    onSuccess: async (wasCheckpoint) => {
      // Always refresh entry data so the revisions panel sees updated diffs.
      await queryClient.invalidateQueries({ queryKey: ["entries"] });
      if (wasCheckpoint) {
        await queryClient.invalidateQueries({ queryKey: ["notebooks"] });
        await queryClient.invalidateQueries({ queryKey: ["revisions"] });
      }
    },
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

  const onEntryDragStart = (event: ReactDragEvent, entry: Entry) => {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/entry-id", entry.id);
    setDraggingEntry({ entryId: entry.id, fromNotebookId: entry.notebook_id });
  };

  const onNotebookDrop = async (event: ReactDragEvent, notebookId: string) => {
    event.preventDefault();

    // External file drop: import .md files as entries
    const files = Array.from(event.dataTransfer.files);
    const mdFiles = files.filter((f) => f.name.endsWith(".md") || f.name.endsWith(".markdown"));
    if (mdFiles.length > 0) {
      setFileDropNotebookId(null);
      for (const file of mdFiles) {
        const markdown = await file.text();
        await importMarkdown.mutateAsync({ notebookId, filename: file.name, markdown });
      }
      return;
    }

    // Internal entry move
    if (!draggingEntry) return;
    setDropNotebookId(null);
    if (draggingEntry.fromNotebookId === notebookId) return;
    await moveEntry.mutateAsync({ entryId: draggingEntry.entryId, notebookId });
  };

  const onEntryFileDrop = async (event: ReactDragEvent, entryId: string) => {
    event.preventDefault();
    setFileDropEntryId(null);
    const files = Array.from(event.dataTransfer.files);
    const nonMdFiles = files.filter((f) => !f.name.endsWith(".md") && !f.name.endsWith(".markdown"));
    for (const file of nonMdFiles) {
      await uploadAttachment.mutateAsync({ entryId, file });
    }
  };

  const hasExternalFiles = (event: ReactDragEvent) => {
    return event.dataTransfer.types.includes("Files");
  };

  const hasMarkdownFiles = (event: ReactDragEvent) => {
    // During dragover we can check types but not filenames in most browsers,
    // so we allow the drop and filter in the handler.
    return event.dataTransfer.types.includes("Files");
  };

  return (
    <div
      className="grid h-full bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100"
      style={{ gridTemplateColumns: `${leftPaneWidth}px 1px minmax(0,1fr) 1px ${rightPaneWidth}px` }}
      onClick={() => setContextMenu(null)}
      onContextMenu={(event) => {
        if (event.target === event.currentTarget) {
          openContextMenu(event, { x: event.clientX, y: event.clientY, kind: "root" });
        }
      }}
    >
      <aside className="flex flex-col border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-sm">
        {/* --- Explorer tree (top) --- */}
        <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
          <span>Explorer</span>
          <div className="flex items-center gap-1">
            <button
              title="New Notebook"
              className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800"
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
              className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800"
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
              <Folder size={14} className="text-slate-500 dark:text-slate-400" />
              <input
                autoFocus
                value={creatingNotebookName}
                onChange={(event) => setCreatingNotebookName(event.target.value)}
                onBlur={submitCreateNotebook}
                onKeyDown={async (event) => {
                  if (event.key === "Enter") await submitCreateNotebook();
                  if (event.key === "Escape") setCreatingNotebookName("");
                }}
                className="w-full border border-slate-300 dark:border-slate-700 px-1 py-0.5 text-sm outline-none dark:bg-slate-950 dark:text-slate-100"
              />
            </div>
          )}

          {notebooksQuery.isLoading && <div className="px-3 py-2 text-slate-500 dark:text-slate-400">Loading...</div>}

          {orderedNotebooks.map((notebook) => {
            const entries = entriesByNotebook[notebook.id] ?? [];
            const expanded = expandedNotebookIds[notebook.id] ?? true;

            return (
              <div key={notebook.id}>
                <div
                  className={`group flex items-center gap-1 px-2 py-1 hover:bg-slate-100 dark:hover:bg-slate-800 ${
                    dropNotebookId === notebook.id || fileDropNotebookId === notebook.id ? "bg-blue-100 dark:bg-blue-900/40" : ""
                  }`}
                  onContextMenu={(event) =>
                    openContextMenu(event, {
                      x: event.clientX,
                      y: event.clientY,
                      kind: "notebook",
                      notebookId: notebook.id,
                    })
                  }
                  onDragOver={(event) => {
                    if (hasExternalFiles(event)) {
                      event.preventDefault();
                      setFileDropNotebookId(notebook.id);
                      return;
                    }
                    if (!draggingEntry || draggingEntry.fromNotebookId === notebook.id) return;
                    event.preventDefault();
                    setDropNotebookId(notebook.id);
                  }}
                  onDragLeave={() => {
                    if (dropNotebookId === notebook.id) setDropNotebookId(null);
                    if (fileDropNotebookId === notebook.id) setFileDropNotebookId(null);
                  }}
                  onDrop={(event) => {
                    void onNotebookDrop(event, notebook.id);
                  }}
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
                  <Folder size={14} className="text-slate-500 dark:text-slate-400" />

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
                      className="w-full border border-slate-300 dark:border-slate-700 px-1 py-0.5 text-sm outline-none dark:bg-slate-950 dark:text-slate-100"
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
                    className="ml-auto hidden p-1 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 group-hover:block"
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
                        <FileText size={14} className="text-slate-500 dark:text-slate-400" />
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
                          className="w-full border border-slate-300 dark:border-slate-700 px-1 py-0.5 text-sm outline-none dark:bg-slate-950 dark:text-slate-100"
                        />
                      </div>
                    )}

                    {entries.map((entry) => (
                      <div key={entry.id}>
                      <div
                        draggable
                        className={`group flex items-center gap-2 py-1 pr-2 ${
                          fileDropEntryId === entry.id || attDropEntryId === entry.id
                            ? "bg-green-100 dark:bg-green-900/40"
                            : selectedEntry?.id === entry.id ? "bg-blue-100 dark:bg-blue-900/40" : "hover:bg-slate-100 dark:hover:bg-slate-800"
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
                        onDragStart={(event) => onEntryDragStart(event, entry)}
                        onDragEnd={() => {
                          setDraggingEntry(null);
                          setDropNotebookId(null);
                        }}
                        onDragOver={(event) => {
                          if (hasExternalFiles(event)) {
                            event.preventDefault();
                            setFileDropEntryId(entry.id);
                            return;
                          }
                          if (draggingAttachment && draggingAttachment.fromEntryId !== entry.id) {
                            event.preventDefault();
                            setAttDropEntryId(entry.id);
                          }
                        }}
                        onDragLeave={() => {
                          if (fileDropEntryId === entry.id) setFileDropEntryId(null);
                          if (attDropEntryId === entry.id) setAttDropEntryId(null);
                        }}
                        onDrop={(event) => {
                          if (hasExternalFiles(event)) {
                            void onEntryFileDrop(event, entry.id);
                            return;
                          }
                          if (draggingAttachment && draggingAttachment.fromEntryId !== entry.id) {
                            event.preventDefault();
                            setAttDropEntryId(null);
                            void moveAttachment.mutateAsync({ attachmentId: draggingAttachment.attachmentId, entryId: entry.id });
                          }
                        }}
                      >
                        <FileText size={14} className="text-slate-500 dark:text-slate-400" />

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
                            className="w-full border border-slate-300 dark:border-slate-700 px-1 py-0.5 text-sm outline-none dark:bg-slate-950 dark:text-slate-100"
                          />
                        ) : (
                          <button className="truncate text-left" onClick={() => setSelectedEntryId(entry.id)}>
                            {entry.title}
                          </button>
                        )}
                      </div>

                      {/* Attachments nested under entry */}
                      {(attachmentsByEntry[entry.id] ?? []).length > 0 && (
                        <div className="pl-6">
                          {(attachmentsByEntry[entry.id] ?? []).map((att) => (
                            <div
                              key={att.id}
                              draggable
                              className="flex items-center gap-2 py-0.5 pr-2 text-xs text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-default"
                              title={`${att.filename} (${(att.size / 1024).toFixed(1)} KB)`}
                              onDoubleClick={() => void downloadAttachment(att.id, att.filename)}
                              onContextMenu={(event) =>
                                openContextMenu(event, {
                                  x: event.clientX,
                                  y: event.clientY,
                                  kind: "attachment",
                                  attachmentId: att.id,
                                  filename: att.filename,
                                })
                              }
                              onDragStart={(event) => {
                                event.dataTransfer.effectAllowed = "move";
                                event.dataTransfer.setData("text/attachment-id", att.id);
                                event.dataTransfer.setData("text/attachment-filename", att.filename);
                                event.dataTransfer.setData("text/attachment-mimetype", att.mime_type);
                                event.stopPropagation();
                                setDraggingAttachment({ attachmentId: att.id, fromEntryId: entry.id });
                              }}
                              onDragEnd={() => {
                                setDraggingAttachment(null);
                                setAttDropEntryId(null);
                              }}
                            >
                              <Paperclip size={12} className="shrink-0" />
                              <span className="truncate">{att.filename}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        </div>{/* end explorer scroll area */}

        {/* --- Horizontal splitter --- */}
        <div
          className="h-px shrink-0 cursor-row-resize bg-slate-300 dark:bg-slate-700 hover:bg-slate-400 dark:hover:bg-slate-600"
          onMouseDown={(event) => {
            dragState.current = {
              side: "revisions",
              startX: event.clientX,
              startY: event.clientY,
              startWidth: 0,
              startHeight: revisionsPaneHeight,
            };
          }}
        />

        {/* --- Revisions panel (bottom) --- */}
        <div className="shrink-0 overflow-hidden" style={{ height: revisionsPaneHeight }}>
          <RevisionsPanel
            entry={selectedEntry}
            activePreviewId={previewRevision?.id ?? null}
            onRestore={() => {
              setPreviewRevision(null);
              setEditorGeneration((n) => n + 1);
            }}
            onPreview={setPreviewRevision}
          />
        </div>
      </aside>

      <div
        className="cursor-col-resize bg-slate-300 dark:bg-slate-700 hover:bg-slate-400 dark:hover:bg-slate-600"
        onMouseDown={(event) => {
          dragState.current = { side: "left", startX: event.clientX, startY: event.clientY, startWidth: leftPaneWidth, startHeight: 0 };
        }}
      />

      <section className="min-h-0 overflow-hidden bg-white dark:bg-slate-900">
        {selectedEntry ? (
          previewRevision ? (
            <EntryEditorForm
              key={`${selectedEntry.id}-preview-${previewRevision.id}`}
              initialTitle={selectedEntry.title}
              initialContent={previewRevision.content_blocks}
              readOnly
              banner={
                <div className="flex items-center justify-between bg-amber-50 dark:bg-amber-900/30 border-b border-amber-200 dark:border-amber-800 px-4 py-1.5 text-xs text-amber-800 dark:text-amber-200">
                  <span>
                    Viewing revision from{" "}
                    {new Date(previewRevision.created_at).toLocaleString(undefined, {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  <button
                    className="font-medium underline hover:no-underline"
                    onClick={() => setPreviewRevision(null)}
                  >
                    Back to current
                  </button>
                </div>
              }
              onSave={async () => {}}
            />
          ) : (
            <EntryEditorForm
              key={`${selectedEntry.id}-${editorGeneration}`}
              initialTitle={selectedEntry.title}
              initialContent={selectedEntry.content_blocks}
              isSaving={saveEntry.isPending}
              onSave={async (payload) => {
                await saveEntry.mutateAsync({
                  id: selectedEntry.id,
                  title: payload.title,
                  content_blocks: payload.content_blocks,
                  checkpoint: payload.checkpoint,
                });
              }}
              uploadFile={async (file: File) => {
                const form = new FormData();
                form.append("entry_id", selectedEntry.id);
                form.append("file", file);
                const { data } = await api.post("/attachments/", form, {
                  headers: { "Content-Type": "multipart/form-data" },
                });
                await queryClient.invalidateQueries({ queryKey: ["attachments"] });
                return `/api/attachments/${data.id}`;
              }}
              onAttachmentDrop={async (drop: AttachmentDropData) => {
                if (drop.altKey) {
                  // Alt+drop: copy the attachment to the current entry
                  const resp = await api.get(`/attachments/${drop.attachmentId}`, {
                    responseType: "blob",
                  });
                  const blob = resp.data as Blob;
                  const file = new File([blob], drop.filename, { type: drop.mimeType });
                  const form = new FormData();
                  form.append("entry_id", selectedEntry.id);
                  form.append("file", file);
                  const { data } = await api.post("/attachments/", form, {
                    headers: { "Content-Type": "multipart/form-data" },
                  });
                  await queryClient.invalidateQueries({ queryKey: ["attachments"] });
                  return `/api/attachments/${data.id}`;
                }
                // Normal drop: reference the existing attachment (no move/copy)
                return `/api/attachments/${drop.attachmentId}`;
              }}
            />
          )
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-500 dark:text-slate-400">
            Create an entry from Explorer to begin.
          </div>
        )}
      </section>

      <div
        className="cursor-col-resize bg-slate-300 dark:bg-slate-700 hover:bg-slate-400 dark:hover:bg-slate-600"
        onMouseDown={(event) => {
          dragState.current = { side: "right", startX: event.clientX, startY: event.clientY, startWidth: rightPaneWidth, startHeight: 0 };
        }}
      />

      <aside className="border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Inspector</div>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Reserved for future tools.</p>
      </aside>

      {contextMenu && (
        <div
          className="fixed z-50 min-w-44 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-1 text-sm shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          {contextMenu.kind === "root" && (
            <button
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
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
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
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
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => {
                  const notebook = orderedNotebooks.find((n) => n.id === contextMenu.notebookId);
                  setContextMenu(null);
                  setRenameState({ kind: "notebook", id: contextMenu.notebookId, value: notebook?.title ?? "" });
                }}
              >
                <Pencil size={14} /> Rename
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-red-700 hover:bg-red-50 dark:hover:bg-red-950/40"
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
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => {
                  setContextMenu(null);
                  setRenameState({ kind: "entry", id: contextMenu.entryId, value: menuEntry?.title ?? "" });
                }}
              >
                <Pencil size={14} /> Rename
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={async () => {
                  setContextMenu(null);
                  const resp = await api.get(`/entries/${contextMenu.entryId}/markdown`, {
                    responseType: "blob",
                  });
                  const disposition = resp.headers["content-disposition"] ?? "";
                  const match = disposition.match(/filename="(.+)"/);
                  const filename = match ? match[1] : "entry.md";
                  const url = URL.createObjectURL(resp.data as Blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = filename;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
              >
                <Download size={14} /> Export as Markdown
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-red-700 hover:bg-red-50 dark:hover:bg-red-950/40"
                onClick={async () => {
                  setContextMenu(null);
                  await deleteEntry.mutateAsync(contextMenu.entryId);
                }}
              >
                <Trash2 size={14} /> Delete
              </button>
            </>
          )}

          {contextMenu.kind === "attachment" && (
            <>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => {
                  setContextMenu(null);
                  void downloadAttachment(contextMenu.attachmentId, contextMenu.filename);
                }}
              >
                <Download size={14} /> Download
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-red-700 hover:bg-red-50 dark:hover:bg-red-950/40"
                onClick={async () => {
                  setContextMenu(null);
                  await deleteAttachment.mutateAsync(contextMenu.attachmentId);
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
