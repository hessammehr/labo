import { useCallback, useEffect, useRef, useState } from "react";
import type { PartialBlock } from "@blocknote/core";
import { useCreateBlockNote, SuggestionMenuController } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";
import { flip, offset, shift, size } from "@floating-ui/react";

type SavePayload = {
  title: string;
  content_blocks: Array<Record<string, unknown>>;
  checkpoint: boolean;
};

export type AttachmentDropData = {
  attachmentId: string;
  filename: string;
  mimeType: string;
  altKey: boolean;
};

type EntryEditorFormProps = {
  initialTitle?: string;
  initialContent?: Array<Record<string, unknown>>;
  isSaving?: boolean;
  readOnly?: boolean;
  banner?: React.ReactNode;
  onSave: (payload: SavePayload) => Promise<void>;
  uploadFile?: (file: File) => Promise<string>;
  onAttachmentDrop?: (data: AttachmentDropData) => Promise<string>;
};

const AUTO_SAVE_DELAY = 2000; // ms

export function EntryEditorForm({
  initialTitle = "",
  initialContent,
  isSaving = false,
  readOnly = false,
  banner,
  onSave,
  uploadFile,
  onAttachmentDrop,
}: EntryEditorFormProps) {
  const [title, setTitle] = useState(initialTitle);
  const titleRef = useRef(title);
  titleRef.current = title;

  // No useEffect to sync initialTitle — the component remounts via key on
  // entry switch, and we don't want server refetches (after auto-save) to
  // reset the title input mid-typing.

  const safeInitialContent =
    Array.isArray(initialContent) && initialContent.length > 0
      ? (initialContent as unknown as PartialBlock[])
      : undefined;

  // Capture initial content once per mount — subsequent prop changes from
  // server refetches (e.g. after auto-save) must not recreate the editor.
  const initialContentRef = useRef(safeInitialContent);

  // Stable ref so the upload callback doesn't recreate the editor.
  const uploadFileRef = useRef(uploadFile);
  uploadFileRef.current = uploadFile;

  const onAttachmentDropRef = useRef(onAttachmentDrop);
  onAttachmentDropRef.current = onAttachmentDrop;

  const editor = useCreateBlockNote(
    {
      ...(initialContentRef.current ? { initialContent: initialContentRef.current } : {}),
      uploadFile: uploadFileRef.current
        ? async (file: File) => {
            return uploadFileRef.current!(file);
          }
        : undefined,
    },
    // Empty dep array: editor is created once; entry switches remount via key.
    [],
  );

  // --- save helpers (disabled in readOnly mode) -----------------------

  const savingRef = useRef(false);
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Stable ref avoids save → scheduleAutoSave → effect cascade on parent re-renders.
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;

  const save = useCallback(
    (checkpoint: boolean) => {
      if (readOnly || savingRef.current) return;
      savingRef.current = true;
      onSaveRef.current({
        title: titleRef.current,
        content_blocks: editor.document as unknown as Array<Record<string, unknown>>,
        checkpoint,
      }).finally(() => {
        savingRef.current = false;
      });
    },
    [editor, readOnly],
  );

  const scheduleAutoSave = useCallback(() => {
    if (readOnly) return;
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = setTimeout(() => save(false), AUTO_SAVE_DELAY);
  }, [save, readOnly]);

  // Keep a stable ref to the latest save so the unmount cleanup can call it.
  const saveRef = useRef(save);
  saveRef.current = save;

  // Flush pending auto-save on unmount (e.g. when switching to revision preview).
  useEffect(() => {
    return () => {
      if (autoSaveTimer.current) {
        clearTimeout(autoSaveTimer.current);
        autoSaveTimer.current = null;
        saveRef.current(false);
      }
    };
  }, []);

  // --- auto-save on editor content change ----------------------------

  useEffect(() => {
    if (readOnly) return;
    const unsubscribe = editor.onChange(() => scheduleAutoSave());
    return unsubscribe;
  }, [editor, scheduleAutoSave, readOnly]);

  // --- auto-save on title change -------------------------------------

  const isFirstTitle = useRef(true);
  useEffect(() => {
    if (readOnly) return;
    // Skip the initial render / reset from prop sync
    if (isFirstTitle.current) {
      isFirstTitle.current = false;
      return;
    }
    scheduleAutoSave();
  }, [title, scheduleAutoSave, readOnly]);

  // --- Cmd+S / Ctrl+S = checkpoint save ------------------------------

  useEffect(() => {
    if (readOnly) return;
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
        save(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [save, readOnly]);

  return (
    <div className="flex h-full flex-col">
      {banner}
      <div className="shrink-0 flex items-center gap-3 border-b border-slate-200 px-4 py-2 dark:border-slate-800">
        <input
          className="w-full border border-slate-300 px-2 py-1 text-lg font-semibold outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 disabled:opacity-60"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Entry title"
          disabled={readOnly}
        />
        {!readOnly && (
          <button
            onClick={() => {
              if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
              save(true);
            }}
            disabled={isSaving}
            className="border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            {isSaving ? "Saving..." : "Save"}
          </button>
        )}
      </div>
      <div
        className="min-h-0 flex-1 overflow-auto"
        onDragOver={(e) => {
          // Prevent browser default (open file) for all drag types over the editor
          e.preventDefault();
        }}
        onDrop={async (e) => {
          // --- Internal attachment drag from tree ---
          const attachmentId = e.dataTransfer.getData("text/attachment-id");
          if (attachmentId && onAttachmentDropRef.current) {
            e.preventDefault();
            const filename = e.dataTransfer.getData("text/attachment-filename");
            const mimeType = e.dataTransfer.getData("text/attachment-mimetype");
            const url = await onAttachmentDropRef.current({
              attachmentId,
              filename,
              mimeType,
              altKey: e.altKey,
            });
            const block: PartialBlock = mimeType.startsWith("image/")
              ? { type: "image", props: { url, name: filename } }
              : { type: "file", props: { url, name: filename } };
            editor.insertBlocks([block], editor.document[editor.document.length - 1], "after");
            return;
          }

          // --- .md file drop: parse and insert as blocks ---
          const files = Array.from(e.dataTransfer.files);
          const mdFiles = files.filter(
            (f) => f.name.endsWith(".md") || f.name.endsWith(".markdown"),
          );
          if (mdFiles.length > 0) {
            e.preventDefault();
            for (const file of mdFiles) {
              const text = await file.text();
              // Parse markdown on the server
              const { data } = await (await import("../lib/api")).api.post<{
                blocks: Array<Record<string, unknown>>;
                title: string | null;
              }>("/entries/parse-markdown", { markdown: text });
              const blocks = data.blocks as unknown as PartialBlock[];
              if (blocks.length > 0) {
                editor.insertBlocks(
                  blocks,
                  editor.document[editor.document.length - 1],
                  "after",
                );
              }
            }
            return;
          }

          // Other files are handled by BlockNote's built-in uploadFile
        }}
      >
        <BlockNoteView editor={editor} editable={!readOnly} slashMenu={false}>
          {!readOnly && (
            <SuggestionMenuController
              triggerCharacter="/"
              floatingUIOptions={{
                useFloatingOptions: {
                  placement: "bottom-start",
                  middleware: [
                    offset(10),
                    flip({ fallbackPlacements: ["top-start"], padding: 10 }),
                    shift({ padding: 10 }),
                    size({
                      apply({ elements, availableHeight }) {
                        elements.floating.style.maxHeight = `${Math.max(0, availableHeight)}px`;
                      },
                      padding: 10,
                    }),
                  ],
                },
              }}
            />
          )}
        </BlockNoteView>
      </div>
    </div>
  );
}
