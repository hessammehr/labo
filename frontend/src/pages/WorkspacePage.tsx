import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  ChevronDown,
  ChevronRight,
  Download,
  Eye,
  FileDown,
  FilePlus2,
  FileText,
  History,
  Image,
  Key,
  Paperclip,
  Pencil,
  Plus,
  Share2,
  Trash2,
  UserCheck,
  X,
} from "lucide-react";

import { EntryEditorForm, type AttachmentDropData } from "../components/EntryEditorForm";
import { LabBook, LabBookPlus } from "../components/icons";
import { usePanels } from "../components/AppShell";
import { RevisionsPanel, type Revision } from "../components/RevisionsPanel";
import { ApiAccessModal } from "../components/ApiAccessModal";
import { ShareModal } from "../components/ShareModal";
import { useIoEvents, ioKey } from "../lib/useIoEvents";
import { useEntryEvents } from "../lib/useEntryEvents";
import { api } from "../lib/api";
import { useSearchSubscribe } from "../lib/searchContext";
import type { Attachment, Entry, Notebook, SearchResult } from "../lib/types";

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
      notebookId: string;
    };

type RenameState =
  | { kind: "notebook"; id: string; value: string }
  | { kind: "entry"; id: string; value: string }
  | { kind: "attachment"; id: string; value: string }
  | null;

const TEXT_MIME_TYPES = new Set([
  "application/json",
  "application/xml",
  "application/xhtml+xml",
  "application/javascript",
  "application/x-sh",
  "application/x-yaml",
  "application/yaml",
  "application/toml",
  "application/x-toml",
  "application/sql",
  "application/graphql",
]);

function isTextMime(mimeType: string): boolean {
  return mimeType.startsWith("text/") || TEXT_MIME_TYPES.has(mimeType);
}

export function WorkspacePage() {
  const { leftOpen, setLeftOpen, rightOpen, setRightOpen, isWide } = usePanels();
  const queryClient = useQueryClient();
  const { indicators: ioIndicators } = useIoEvents(
    (event) => {
      if (event.direction === "write") {
        void queryClient.invalidateQueries({ queryKey: ["attachments", "entry", event.entry_id] });
      }
    }
  );
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [editorGeneration, setEditorGeneration] = useState(0);
  const [previewRevision, setPreviewRevision] = useState<Revision | null>(null);
  const [entryVersionById, setEntryVersionById] = useState<Record<string, number>>({});
  const [isEditorDirty, setIsEditorDirty] = useState(false);
  const [remoteAheadVersion, setRemoteAheadVersion] = useState<number | null>(null);
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
  const [fileDropExplorer, setFileDropExplorer] = useState(false);
  const [draggingAttachment, setDraggingAttachment] = useState<{ attachmentId: string; fromEntryId: string } | null>(null);
  const [attDropEntryId, setAttDropEntryId] = useState<string | null>(null);
  const [selectedAttachmentId, setSelectedAttachmentId] = useState<string | null>(null);
  const [shareModal, setShareModal] = useState<{
    resourceId: string;
    resourceName: string;
  } | null>(null);
  const [apiAccessModal, setApiAccessModal] = useState<{
    resourceId: string;
    resourceType: "notebook" | "entry";
    resourceName: string;
  } | null>(null);

  const [leftPaneWidth, setLeftPaneWidth] = useState(320);
  const [rightPaneWidth, setRightPaneWidth] = useState(280);
  const [revisionsPaneHeight, setRevisionsPaneHeight] = useState(200);
  const [previewPaneHeight, setPreviewPaneHeight] = useState(200);
  const [previewCollapsed, setPreviewCollapsed] = useState(false);
  const [revisionsCollapsed, setRevisionsCollapsed] = useState(false);
  const laboImportInputRef = useRef<HTMLInputElement>(null);
  const dragState = useRef<{
    side: "left" | "right" | "revisions" | "preview";
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
      } else if (dragState.current.side === "revisions") {
        const next = dragState.current.startHeight - (event.clientY - dragState.current.startY);
        setRevisionsPaneHeight(Math.max(80, Math.min(500, next)));
      } else {
        const next = dragState.current.startHeight - (event.clientY - dragState.current.startY);
        setPreviewPaneHeight(Math.max(80, Math.min(500, next)));
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

  // Helper: switch entry and clear dependent state.
  const selectEntry = (entryId: string | null) => {
    setSelectedEntryId(entryId);
    setSelectedAttachmentId(null);
    setPreviewRevision(null);
    setIsEditorDirty(false);
    setRemoteAheadVersion(null);
    // When the sidebar is an overlay, close it after selecting an entry
    if (!isWide) setLeftOpen(false);
  };

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

  useEntryEvents((event) => {
    setEntryVersionById((prev) => {
      const known = prev[event.entry_id] ?? 0;
      if (event.version <= known) return prev;
      return { ...prev, [event.entry_id]: event.version };
    });

    if (!selectedEntry || previewRevision) return;
    if (event.entry_id !== selectedEntry.id) return;

    if (event.version <= selectedEntry.version) return;

    if (isEditorDirty) {
      // Avoid transient "paused" flicker from our own in-flight save events.
      if (!saveEntry.isPending) {
        setRemoteAheadVersion(event.version);
      }
      return;
    }

    void (async () => {
      const { data: fresh } = await api.get<Entry>(`/entries/${selectedEntry.id}`);
      queryClient.setQueryData<Entry[]>(
        ["entries", "notebook", fresh.notebook_id],
        (old) => old?.map((e) => (e.id === fresh.id ? fresh : e)) ?? old,
      );
      setRemoteAheadVersion(null);
      setEditorGeneration((n) => n + 1);
    })();
  });

  const selectedAttachment = useMemo(() => {
    if (!selectedAttachmentId) return null;
    for (const atts of Object.values(attachmentsByEntry)) {
      const found = atts.find((a) => a.id === selectedAttachmentId);
      if (found) return found;
    }
    return null;
  }, [selectedAttachmentId, attachmentsByEntry]);

  const isText = selectedAttachment
    ? isTextMime(selectedAttachment.mime_type)
    : false;

  // Fetch text content for text-ish attachments.
  const textAttachmentId = isText ? selectedAttachment?.id ?? null : null;
  const textPreview = useQuery({
    queryKey: ["attachment-text", textAttachmentId],
    queryFn: async () => {
      const res = await fetch(`/api/attachments/${textAttachmentId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.text();
    },
    enabled: textAttachmentId !== null,
    staleTime: 30_000,
  });



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
      selectEntry(entry.id);
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

  const importLaboArchive = useMutation({
    mutationFn: async ({ notebookId, file }: { notebookId?: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      const url = notebookId
        ? `/notebooks/import-labo?notebook_id=${notebookId}`
        : "/notebooks/import-labo";
      const { data } = await api.post<{ kind: string; notebook_id: string; entry_ids: string[] }>(
        url,
        form,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      return data;
    },
    onSuccess: async (result) => {
      await refreshTree();
      setExpandedNotebookIds((prev) => ({ ...prev, [result.notebook_id]: true }));
      if (result.entry_ids.length > 0) selectEntry(result.entry_ids[0]);
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
      selectEntry(entry.id);
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

  const renameAttachment = useMutation({
    mutationFn: async ({ attachmentId, filename }: { attachmentId: string; filename: string }) => {
      await api.patch(`/attachments/${attachmentId}`, { filename });
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

  const exportResource = async (
    kind: "entry" | "notebook",
    id: string,
    title: string,
    format: string,
  ) => {
    const endpoint =
      kind === "entry"
        ? `/entries/${id}/export?format=${format}`
        : `/notebooks/${id}/export?format=${format}`;
    const resp = await api.get(endpoint, { responseType: "blob" });
    // Prefer server-provided filename from Content-Disposition header
    const disposition = resp.headers["content-disposition"] ?? "";
    const match = disposition.match(/filename="(.+)"/);
    const fallbackExt =
      { md: ".md", html: ".html", pdf: ".pdf", docx: ".docx", latex: ".tex", labo: ".zip" }[format] ?? "";
    const filename = match ? match[1] : title.replace(/ /g, "_") + fallbackExt;
    const url = URL.createObjectURL(resp.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportFormats = (hasAttachments: boolean) => {
    const formats = [
      { key: "md", label: hasAttachments ? "Markdown (.zip)" : "Markdown (.md)" },
      { key: "html", label: "HTML (.html)" },
      { key: "pdf", label: "PDF (.pdf)" },
      { key: "docx", label: "Word (.docx)" },
      { key: "latex", label: hasAttachments ? "LaTeX (.zip)" : "LaTeX (.tex)" },
      { key: "labo", label: "Labo Archive (.zip)" },
    ];
    if (hasAttachments) {
      formats.push({ key: "attachments", label: "Attachments (.zip)" });
    }
    return formats;
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
      expected_version?: number;
    }) => {
      const { data } = await api.put<Entry>(`/entries/${payload.id}`, {
        title: payload.title,
        content_blocks: payload.content_blocks,
        checkpoint: payload.checkpoint,
        expected_version: payload.expected_version,
        change_summary: payload.checkpoint ? "Saved in workspace" : "",
      });
      return { entry: data, wasCheckpoint: payload.checkpoint };
    },
    onSuccess: async ({ entry, wasCheckpoint }) => {
      setEntryVersionById((prev) => ({ ...prev, [entry.id]: entry.version }));
      if (selectedEntryId === entry.id) {
        setRemoteAheadVersion(null);
      }
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
    } else if (renameState.kind === "entry") {
      await renameEntry.mutateAsync({ entryId: renameState.id, title: value });
    } else if (renameState.kind === "attachment") {
      await renameAttachment.mutateAsync({ attachmentId: renameState.id, filename: value });
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

    // External file drop: import Labo Archives
    // Notebook archives always create a new notebook; entry archives are
    // imported into the drop target.  The backend decides based on the manifest.
    const zipFiles = files.filter((f) => f.name.endsWith(".zip"));
    if (zipFiles.length > 0) {
      setFileDropNotebookId(null);
      for (const file of zipFiles) {
        await importLaboArchive.mutateAsync({ notebookId, file });
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

  /** Whether the current user has write access to a notebook based on its sharing_level. */
  const canWriteNotebook = (notebookId: string): boolean => {
    const notebook = orderedNotebooks.find((n) => n.id === notebookId);
    if (!notebook) return false;
    const level = notebook.sharing_level;
    // null = own notebook (not shared), "shared_by_me" = own notebook shared with others,
    // "owner" = co-owner, "write" = editor → all writable.
    // "read" = viewer → read-only.
    return level !== "read";
  };

  // Subscribe to search selections from the header search bar
  const subscribeSearch = useSearchSubscribe();
  useEffect(() => {
    return subscribeSearch((result: SearchResult) => {
      if (result.type === "entry" && result.notebook_id) {
        setExpandedNotebookIds((prev) => ({ ...prev, [result.notebook_id!]: true }));
        selectEntry(result.id);
      } else if (result.type === "notebook") {
        setExpandedNotebookIds((prev) => ({ ...prev, [result.id]: true }));
      }
    });
  }, [subscribeSearch]); // eslint-disable-line react-hooks/exhaustive-deps

  const SharingIcon = ({ level }: { level: string | null }) => {
    if (!level) return null;
    // Current user shared this item with others
    if (level === "shared_by_me") return <Share2 size={12} className="shrink-0 text-blue-500" aria-label="Shared by you" />;
    // Current user is a recipient – show their access level
    if (level === "owner") return <UserCheck size={12} className="shrink-0 text-amber-500" aria-label="Shared with you (co-owner)" />;
    if (level === "write") return <Pencil size={12} className="shrink-0 text-blue-500" aria-label="Shared with you (editor)" />;
    return <Eye size={12} className="shrink-0 text-slate-400" aria-label="Shared with you (viewer)" />;
  };

  return (
    <div
      className="relative h-full overflow-hidden bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 grid"
      style={{
        gridTemplateColumns: [
          leftOpen && isWide ? `${leftPaneWidth}px 1px` : "auto",
          "minmax(0,1fr)",
          rightOpen && isWide ? `1px ${rightPaneWidth}px` : "auto",
        ].join(" "),
      }}
      onClick={() => { setContextMenu(null); }}
      onContextMenu={(event) => {
        if (event.target === event.currentTarget) {
          openContextMenu(event, { x: event.clientX, y: event.clientY, kind: "root" });
        }
      }}
    >
      {/* Overlay backdrop — shown when any panel is open as overlay (narrow viewport) */}
      {!isWide && (leftOpen || rightOpen) && (
        <div
          className="panel-backdrop"
          onClick={() => { setLeftOpen(false); setRightOpen(false); }}
        />
      )}

      {/* Left panel — wide: edge tab or inline panel; narrow: edge tab in grid + overlay drawer */}
      {(isWide ? !leftOpen : true) && (
        <button
          onClick={() => setLeftOpen(true)}
          className="edge-tab edge-tab-left"
          aria-label="Open explorer"
        >
          <span>Explorer</span>
        </button>
      )}

      {(isWide ? leftOpen : true) && (
      <aside
        className={`flex flex-col min-h-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-sm ${
          isWide
            ? ""
            : `panel-drawer panel-drawer-left ${leftOpen ? "panel-drawer-open" : ""}`
        }`}
      >
        {/* --- Explorer tree (top) --- */}
        <div
          className={`min-h-0 flex-1 overflow-y-auto${fileDropExplorer ? " ring-2 ring-inset ring-blue-400 dark:ring-blue-500" : ""}`}
          onContextMenu={(event) => {
            event.preventDefault();
            openContextMenu(event, { x: event.clientX, y: event.clientY, kind: "root" });
          }}
          onDragOver={(event) => {
            if (hasExternalFiles(event)) {
              event.preventDefault();
              setFileDropExplorer(true);
            }
          }}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node)) {
              setFileDropExplorer(false);
            }
          }}
          onDrop={async (event) => {
            event.preventDefault();
            setFileDropExplorer(false);
            const files = Array.from(event.dataTransfer.files);
            const zipFiles = files.filter((f) => f.name.endsWith(".zip"));
            for (const file of zipFiles) {
              await importLaboArchive.mutateAsync({ file }); // no notebookId → create new notebook
            }
          }}
        >
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
              <LabBookPlus size={14} />
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
            <button
              title="Close explorer"
              className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded"
              onClick={() => setLeftOpen(false)}
            >
              <X size={14} />
            </button>
          </div>
        </div>

        <div className="py-1">
          {creatingNotebookName !== "" && (
            <div className="flex items-center gap-2 px-3 py-1">
              <LabBook size={14} className="text-slate-500 dark:text-slate-400" />
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
                  onContextMenu={(event) => {
                    event.stopPropagation();
                    openContextMenu(event, {
                      x: event.clientX,
                      y: event.clientY,
                      kind: "notebook",
                      notebookId: notebook.id,
                    });
                  }}
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
                    event.stopPropagation();
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
                  <LabBook size={14} className="text-slate-500 dark:text-slate-400" />

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
                        if (entries[0]) { selectEntry(entries[0].id); }
                      }}
                    >
                      {notebook.title}
                    </button>
                  )}

                  <SharingIcon level={notebook.sharing_level} />

                  <button
                    className="ml-auto p-1 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 hidden group-hover:block [@media(hover:none)]:block"
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
                        onContextMenu={(event) => {
                          event.stopPropagation();
                          openContextMenu(event, {
                            x: event.clientX,
                            y: event.clientY,
                            kind: "entry",
                            entryId: entry.id,
                            notebookId: notebook.id,
                          });
                        }}
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
                          event.stopPropagation();
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
                          <button className="truncate text-left" onClick={() => { selectEntry(entry.id); }}>
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
                              className={`flex items-center gap-2 py-0.5 pr-2 text-xs text-slate-500 dark:text-slate-400 cursor-default ${
                                selectedAttachmentId === att.id
                                  ? "bg-blue-100 dark:bg-blue-900/40"
                                  : "hover:bg-slate-100 dark:hover:bg-slate-800"
                              }`}
                              title={`${att.filename} (${(att.size / 1024).toFixed(1)} KB)`}
                              onClick={() => setSelectedAttachmentId(att.id)}
                              onDoubleClick={() => void downloadAttachment(att.id, att.filename)}
                              onContextMenu={(event) => {
                                event.stopPropagation();
                                openContextMenu(event, {
                                  x: event.clientX,
                                  y: event.clientY,
                                  kind: "attachment",
                                  attachmentId: att.id,
                                  filename: att.filename,
                                  notebookId: notebook.id,
                                });
                              }}
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
                              {ioIndicators[ioKey(entry.id, att.filename)] ? (
                                <img
                                  src={ioIndicators[ioKey(entry.id, att.filename)].direction === "write" ? "/downloading.svg" : "/uploading.svg"}
                                  alt={ioIndicators[ioKey(entry.id, att.filename)].direction === "write" ? "Writing" : "Reading"}
                                  className="shrink-0 h-3 w-3"
                                />
                              ) : (
                                <Paperclip size={12} className="shrink-0" />
                              )}
                              {renameState?.kind === "attachment" && renameState.id === att.id ? (
                                <input
                                  autoFocus
                                  value={renameState.value}
                                  onChange={(event) =>
                                    setRenameState({ kind: "attachment", id: att.id, value: event.target.value })
                                  }
                                  onBlur={submitRename}
                                  onKeyDown={async (event) => {
                                    if (event.key === "Enter") await submitRename();
                                    if (event.key === "Escape") setRenameState(null);
                                  }}
                                  className="w-full border border-slate-300 dark:border-slate-700 px-1 py-0.5 text-xs outline-none dark:bg-slate-950 dark:text-slate-100"
                                />
                              ) : (
                                <span className="truncate">{att.filename}</span>
                              )}
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

        {/* --- Preview section header (always visible) --- */}
        <div
          className="shrink-0 flex items-center gap-1.5 border-y border-slate-200 dark:border-slate-800 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300 cursor-pointer select-none hover:bg-slate-50 dark:hover:bg-slate-800/60"
          onClick={() => setPreviewCollapsed((c) => !c)}
        >
          {previewCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
          {selectedAttachment && isText ? <FileText size={12} /> : <Image size={12} />}
          <span>Preview</span>
          {selectedAttachment && (
            <span className="ml-auto font-normal normal-case tracking-normal text-[10px] text-slate-400 dark:text-slate-500 truncate max-w-[50%]">
              {selectedAttachment.filename} · {(selectedAttachment.size / 1024).toFixed(1)} KB
            </span>
          )}
        </div>

        {!previewCollapsed && (
          <>
            {/* Preview pane body */}
            <div className="shrink-0 overflow-hidden flex flex-col" style={{ height: previewPaneHeight }}>
              {selectedAttachment && selectedAttachment.mime_type.startsWith("image/") ? (
                <div className="flex-1 min-h-0 flex items-center justify-center p-2 bg-slate-50 dark:bg-slate-950/50">
                  <img
                    src={`/api/attachments/${selectedAttachment.id}`}
                    alt={selectedAttachment.filename}
                    className="max-w-full max-h-full object-contain rounded"
                  />
                </div>
              ) : selectedAttachment && isText ? (
                <div className="flex-1 min-h-0 overflow-auto p-2 bg-slate-50 dark:bg-slate-950/50">
                  {textPreview.isLoading ? (
                    <div className="flex items-center justify-center h-full text-xs text-slate-400 dark:text-slate-500">Loading…</div>
                  ) : textPreview.isError ? (
                    <div className="flex items-center justify-center h-full text-xs text-red-400 dark:text-red-500">{String(textPreview.error)}</div>
                  ) : (
                    <pre className="text-xs font-mono text-slate-700 dark:text-slate-300 whitespace-pre overflow-x-auto m-0">{textPreview.data}</pre>
                  )}
                </div>
              ) : (
                <div className="flex-1 min-h-0 flex items-center justify-center p-2 text-xs text-slate-400 dark:text-slate-500">
                  {selectedAttachment ? "No preview available" : "Select an attachment to preview"}
                </div>
              )}
            </div>

            {/* Preview ↔ Revisions splitter */}
            <div
              className="row-splitter shrink-0 cursor-row-resize bg-slate-300 dark:bg-slate-700 hover:bg-slate-400 dark:hover:bg-slate-600"
              onMouseDown={(event) => {
                dragState.current = {
                  side: "preview",
                  startX: event.clientX,
                  startY: event.clientY,
                  startWidth: 0,
                  startHeight: previewPaneHeight,
                };
              }}
            />
          </>
        )}

        {/* --- Revisions section header --- */}
        <div
          className="shrink-0 flex items-center gap-1.5 border-y border-slate-200 dark:border-slate-800 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300 cursor-pointer select-none hover:bg-slate-50 dark:hover:bg-slate-800/60"
          onClick={() => setRevisionsCollapsed((c) => !c)}
        >
          {revisionsCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
          <History size={12} />
          <span>Revisions</span>
        </div>

        {!revisionsCollapsed && (
          <>
            {/* Revisions splitter */}
            <div
              className="row-splitter shrink-0 cursor-row-resize bg-slate-300 dark:bg-slate-700 hover:bg-slate-400 dark:hover:bg-slate-600"
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

            {/* Revisions panel body */}
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
          </>
        )}
      </aside>
      )}

      {isWide && leftOpen && (
        <div
          className="col-splitter cursor-col-resize bg-slate-300 dark:bg-slate-700 hover:bg-slate-400 dark:hover:bg-slate-600"
          onMouseDown={(event) => {
            dragState.current = { side: "left", startX: event.clientX, startY: event.clientY, startWidth: leftPaneWidth, startHeight: 0 };
          }}
        />
      )}

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
              suspendAutoSave={Boolean(remoteAheadVersion && isEditorDirty && !saveEntry.isPending)}
              onDirtyChange={setIsEditorDirty}
              banner={
                remoteAheadVersion && isEditorDirty && !saveEntry.isPending ? (
                  <div className="flex items-center justify-between bg-amber-50 dark:bg-amber-900/30 border-b border-amber-200 dark:border-amber-800 px-4 py-1.5 text-xs text-amber-800 dark:text-amber-200">
                    <span>
                      Newer version detected (v{remoteAheadVersion}). Auto-save is paused until you reload.
                    </span>
                    <button
                      className="font-medium underline hover:no-underline"
                      onClick={async () => {
                        await queryClient.refetchQueries({ queryKey: ["entries"] });
                        setRemoteAheadVersion(null);
                        setEditorGeneration((n) => n + 1);
                      }}
                    >
                      Reload latest
                    </button>
                  </div>
                ) : undefined
              }
              onSave={async (payload) => {
                const doSave = async (expectedVersion?: number) => {
                  await saveEntry.mutateAsync({
                    id: selectedEntry.id,
                    title: payload.title,
                    content_blocks: payload.content_blocks,
                    checkpoint: payload.checkpoint,
                    expected_version: expectedVersion,
                  });
                };

                const expectedVersion = Math.max(
                  entryVersionById[selectedEntry.id] ?? 0,
                  selectedEntry.version,
                );

                try {
                  await doSave(expectedVersion);
                } catch (error) {
                  if (isAxiosError(error) && error.response?.status === 409) {
                    const currentVersion = error.response.data?.detail?.current_version;
                    if (typeof currentVersion === "number") {
                      setRemoteAheadVersion(currentVersion);
                    }

                    if (payload.checkpoint) {
                      const reload = window.confirm(
                        "This entry changed on another session. Reload the latest version now?",
                      );
                      if (reload) {
                        await queryClient.refetchQueries({ queryKey: ["entries"] });
                        setRemoteAheadVersion(null);
                        setEditorGeneration((n) => n + 1);
                      }
                    }
                    return;
                  }
                  throw error;
                }
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
              onExportSvgAttachment={async (blob: Blob, filename: string) => {
                const form = new FormData();
                form.append("entry_id", selectedEntry.id);
                form.append("file", new File([blob], filename, { type: "image/svg+xml" }));
                await api.post("/attachments/", form, {
                  headers: { "Content-Type": "multipart/form-data" },
                });
                await queryClient.invalidateQueries({ queryKey: ["attachments"] });
              }}
            />
          )
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-500 dark:text-slate-400">
            Create an entry from Explorer to begin.
          </div>
        )}
      </section>

      {/* Right panel — wide: edge tab or inline panel; narrow: edge tab in grid + overlay drawer */}
      {(isWide ? rightOpen : false) && (
        <div
          className="col-splitter cursor-col-resize bg-slate-300 dark:bg-slate-700 hover:bg-slate-400 dark:hover:bg-slate-600"
          onMouseDown={(event) => {
            dragState.current = { side: "right", startX: event.clientX, startY: event.clientY, startWidth: rightPaneWidth, startHeight: 0 };
          }}
        />
      )}

      {(isWide ? !rightOpen : true) && (
        <button
          onClick={() => setRightOpen(true)}
          className="edge-tab edge-tab-right"
          aria-label="Open inspector"
        >
          <span>Inspector</span>
        </button>
      )}

      {(isWide ? rightOpen : true) && (
        <aside
          className={`border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 ${
            isWide
              ? ""
              : `panel-drawer panel-drawer-right ${rightOpen ? "panel-drawer-open" : ""}`
          }`}
        >
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
            <span>Inspector</span>
            <button
              title="Close inspector"
              className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded"
              onClick={() => setRightOpen(false)}
            >
              <X size={14} />
            </button>
          </div>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Reserved for future tools.</p>
        </aside>
      )}

      {contextMenu && (
        <div
          className="fixed z-50 min-w-44 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-1 text-sm shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          {contextMenu.kind === "root" && (
            <>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => {
                  setContextMenu(null);
                  setCreatingNotebookName("Untitled Notebook");
                  setRenameState(null);
                }}
              >
                <LabBookPlus size={14} /> New Notebook
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => {
                  setContextMenu(null);
                  laboImportInputRef.current?.click();
                }}
              >
                <FileDown size={14} /> Import Labo Archive…
              </button>
            </>
          )}

          {contextMenu.kind === "notebook" && (
            <>
              {canWriteNotebook(contextMenu.notebookId) && (
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
              )}
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => {
                  const notebook = orderedNotebooks.find((n) => n.id === contextMenu.notebookId);
                  setContextMenu(null);
                  setShareModal({
                    resourceId: contextMenu.notebookId,
                    resourceName: notebook?.title ?? "Notebook",
                  });
                }}
              >
                <Share2 size={14} /> Share…
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => {
                  const notebook = orderedNotebooks.find((n) => n.id === contextMenu.notebookId);
                  setContextMenu(null);
                  setApiAccessModal({
                    resourceId: contextMenu.notebookId,
                    resourceType: "notebook",
                    resourceName: notebook?.title ?? "Notebook",
                  });
                }}
              >
                <Key size={14} /> API Access…
              </button>
              {/* Export submenu for notebook */}
              <div className="group/export relative">
                <div className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800 cursor-default">
                  <FileDown size={14} /> Export
                  <ChevronRight size={12} className="ml-auto" />
                </div>
                <div className="invisible group-hover/export:visible absolute left-full top-0 z-50 min-w-48 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-1 text-sm shadow-lg">
                  {exportFormats(
                    (entriesByNotebook[contextMenu.notebookId] ?? []).some(
                      (e) => (attachmentsByEntry[e.id] ?? []).length > 0,
                    ),
                  ).map(({ key, label }) => (
                    <button
                      key={key}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                      onClick={async () => {
                        const notebook = orderedNotebooks.find((n) => n.id === contextMenu.notebookId);
                        setContextMenu(null);
                        await exportResource("notebook", contextMenu.notebookId, notebook?.title ?? "Notebook", key);
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              {canWriteNotebook(contextMenu.notebookId) && (
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
              )}
              {canWriteNotebook(contextMenu.notebookId) && (
                <button
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-red-700 hover:bg-red-50 dark:hover:bg-red-950/40"
                  onClick={async () => {
                    setContextMenu(null);
                    await deleteNotebook.mutateAsync(contextMenu.notebookId);
                  }}
                >
                  <Trash2 size={14} /> Delete
                </button>
              )}
            </>
          )}

          {contextMenu.kind === "entry" && (
            <>
              {canWriteNotebook(contextMenu.notebookId) && (
                <button
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                  onClick={() => {
                    setContextMenu(null);
                    setRenameState({ kind: "entry", id: contextMenu.entryId, value: menuEntry?.title ?? "" });
                  }}
                >
                  <Pencil size={14} /> Rename
                </button>
              )}
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => {
                  setContextMenu(null);
                  setApiAccessModal({
                    resourceId: contextMenu.entryId,
                    resourceType: "entry",
                    resourceName: menuEntry?.title ?? "Entry",
                  });
                }}
              >
                <Key size={14} /> API Access…
              </button>
              {/* Export submenu for entry */}
              <div className="group/export relative">
                <div className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800 cursor-default">
                  <FileDown size={14} /> Export
                  <ChevronRight size={12} className="ml-auto" />
                </div>
                <div className="invisible group-hover/export:visible absolute left-full top-0 z-50 min-w-48 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-1 text-sm shadow-lg">
                  {exportFormats(
                    (attachmentsByEntry[contextMenu.entryId] ?? []).length > 0,
                  ).map(({ key, label }) => (
                    <button
                      key={key}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                      onClick={async () => {
                        setContextMenu(null);
                        await exportResource("entry", contextMenu.entryId, menuEntry?.title ?? "Entry", key);
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              {canWriteNotebook(contextMenu.notebookId) && (
                <button
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-red-700 hover:bg-red-50 dark:hover:bg-red-950/40"
                  onClick={async () => {
                    setContextMenu(null);
                    await deleteEntry.mutateAsync(contextMenu.entryId);
                  }}
                >
                  <Trash2 size={14} /> Delete
                </button>
              )}
            </>
          )}

          {contextMenu.kind === "attachment" && (
            <>
              {canWriteNotebook(contextMenu.notebookId) && (
                <button
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                  onClick={() => {
                    setContextMenu(null);
                    setRenameState({ kind: "attachment", id: contextMenu.attachmentId, value: contextMenu.filename });
                  }}
                >
                  <Pencil size={14} /> Rename
                </button>
              )}
              <button
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => {
                  setContextMenu(null);
                  void downloadAttachment(contextMenu.attachmentId, contextMenu.filename);
                }}
              >
                <Download size={14} /> Download
              </button>
              {canWriteNotebook(contextMenu.notebookId) && (
                <button
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-red-700 hover:bg-red-50 dark:hover:bg-red-950/40"
                  onClick={async () => {
                    setContextMenu(null);
                    await deleteAttachment.mutateAsync(contextMenu.attachmentId);
                  }}
                >
                  <Trash2 size={14} /> Delete
                </button>
              )}
            </>
          )}
        </div>
      )}

      {/* Hidden file input for importing notebook-level Labo Archives */}
      <input
        ref={laboImportInputRef}
        type="file"
        accept=".zip"
        className="hidden"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = ""; // reset so the same file can be re-selected
          if (!file) return;
          await importLaboArchive.mutateAsync({ file });
        }}
      />

      {shareModal && (
        <ShareModal
          resourceId={shareModal.resourceId}
          resourceName={shareModal.resourceName}
          onClose={() => setShareModal(null)}
        />
      )}

      {apiAccessModal && (
        <ApiAccessModal
          resourceId={apiAccessModal.resourceId}
          resourceType={apiAccessModal.resourceType}
          resourceName={apiAccessModal.resourceName}
          onClose={() => setApiAccessModal(null)}
        />
      )}

    </div>
  );
}
