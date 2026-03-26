import { useCallback, useEffect, useRef, useState } from "react";
import {
  BlockNoteSchema,
  defaultBlockSpecs,
  createHeadingBlockSpec,
  type PartialBlock,
} from "@blocknote/core";
import {
  useCreateBlockNote,
  SuggestionMenuController,
  getDefaultReactSlashMenuItems,
  FormattingToolbarController,
  FormattingToolbar,
  getFormattingToolbarItems,
  FileCaptionButton,
  FileDeleteButton,
  FileRenameButton,
  FilePreviewButton,
  TextAlignButton,
  useBlockNoteEditor,
  useEditorState,
} from "@blocknote/react";
import type { BlockSchema, InlineContentSchema, StyleSchema } from "@blocknote/core";
import { BlockNoteView } from "@blocknote/mantine";
import { flip, offset, shift, size } from "@floating-ui/react";
import { FlaskConical, GitCommitHorizontal } from "lucide-react";
import { ChemStructureBlock } from "../lib/chemBlock";
import {
  ChemReplaceButton,
  ChemDownloadButton,
  ChemAttachmentButton,
} from "../lib/chemToolbar";
import { KetcherModal } from "./KetcherModal";

// ── Custom formatting toolbar ─────────────────────────────────────────
// Shows chem-specific buttons when a chemStructure block is selected,
// otherwise falls back to the default button set.

const CustomFormattingToolbar = () => {
  const editor = useBlockNoteEditor<BlockSchema, InlineContentSchema, StyleSchema>();
  const isChemSelected = useEditorState({
    editor,
    selector: ({ editor }) => {
      const blocks = editor.getSelection()?.blocks || [
        editor.getTextCursorPosition().block,
      ];
      return blocks.length === 1 && blocks[0].type === "chemStructure";
    },
  });

  if (isChemSelected) {
    return (
      <FormattingToolbar>
        <FileCaptionButton key="caption" />
        <ChemReplaceButton key="replace" />
        <FileRenameButton key="rename" />
        <FileDeleteButton key="delete" />
        <ChemDownloadButton key="download" />
        <ChemAttachmentButton key="attachment" />
        <FilePreviewButton key="preview" />
        <TextAlignButton textAlignment="left" key="alignLeft" />
        <TextAlignButton textAlignment="center" key="alignCenter" />
        <TextAlignButton textAlignment="right" key="alignRight" />
      </FormattingToolbar>
    );
  }

  // Default toolbar for text / image / file blocks — use the full built-in set
  return <FormattingToolbar>{getFormattingToolbarItems()}</FormattingToolbar>;
};

// ── Custom schema with chem block ─────────────────────────────────────
const schema = BlockNoteSchema.create({
  blockSpecs: {
    ...defaultBlockSpecs,
    // Override heading to exclude H1 (the entry title serves as H1)
    heading: createHeadingBlockSpec({ levels: [2, 3], defaultLevel: 2 }),
    chemStructure: ChemStructureBlock(),
  },
});

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
  /** Called when user right-clicks a structure and picks "Save to notebook" */
  onExportSvgAttachment?: (svgBlob: Blob, filename: string) => void;
};

const AUTO_SAVE_DELAY = 2000; // ms

// ── Ketcher modal state ───────────────────────────────────────────────
type KetcherState = {
  open: boolean;
  blockId: string;
  ket: string;
};

const KETCHER_CLOSED: KetcherState = { open: false, blockId: "", ket: "" };

/** Read the current theme from the .dark class on <html> (Tailwind convention). */
function useDarkMode(): boolean {
  const [dark, setDark] = useState(
    () => document.documentElement.classList.contains("dark"),
  );
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setDark(document.documentElement.classList.contains("dark"));
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);
  return dark;
}

export function EntryEditorForm({
  initialTitle = "",
  initialContent,
  isSaving = false,
  readOnly = false,
  banner,
  onSave,
  uploadFile,
  onAttachmentDrop,
  onExportSvgAttachment,
}: EntryEditorFormProps) {
  const dark = useDarkMode();
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
      schema,
      ...(initialContentRef.current ? { initialContent: initialContentRef.current as any } : {}),
      uploadFile: uploadFileRef.current
        ? async (file: File) => {
            return uploadFileRef.current!(file);
          }
        : undefined,
    },
    // Empty dep array: editor is created once; entry switches remount via key.
    [],
  );

  // --- Ketcher modal state -------------------------------------------

  const [ketcher, setKetcher] = useState<KetcherState>(KETCHER_CLOSED);

  // Listen for "open-ketcher" custom events dispatched by the chem block
  useEffect(() => {
    const handler = (e: Event) => {
      const { blockId, ket } = (e as CustomEvent).detail;
      setKetcher({ open: true, blockId, ket });
    };
    window.addEventListener("open-ketcher", handler);
    return () => window.removeEventListener("open-ketcher", handler);
  }, []);

  const handleKetcherSave = useCallback(
    (ket: string, smiles: string, svg: string) => {
      // Set url to a data-URI so built-in File* toolbar buttons activate.
      const url = svg
        ? `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`
        : "";
      editor.updateBlock(ketcher.blockId, {
        props: { ket, smiles, svgPreview: svg, url },
      });
      setKetcher(KETCHER_CLOSED);
    },
    [editor, ketcher.blockId],
  );

  const handleKetcherClose = useCallback(() => {
    setKetcher(KETCHER_CLOSED);
  }, []);

  // --- SVG export from structure context menu -------------------------

  const onExportSvgAttachmentRef = useRef(onExportSvgAttachment);
  onExportSvgAttachmentRef.current = onExportSvgAttachment;

  useEffect(() => {
    const handler = (e: Event) => {
      const { svgPreview, action, filename: eventFilename } = (e as CustomEvent).detail as {
        svgPreview: string;
        action: "download" | "attachment";
        filename?: string;
      };
      if (!svgPreview) return;
      const blob = new Blob([svgPreview], { type: "image/svg+xml" });
      const filename = eventFilename || `structure-${Date.now()}.svg`;

      if (action === "download") {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
      } else if (action === "attachment" && onExportSvgAttachmentRef.current) {
        onExportSvgAttachmentRef.current(blob, filename);
      }
    };
    window.addEventListener("chem-export-svg", handler);
    return () => window.removeEventListener("chem-export-svg", handler);
  }, []);

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
          className="w-full rounded border border-slate-300 px-2 py-1 text-lg font-semibold outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 disabled:opacity-60"
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
            title="Create revision"
            className="rounded border border-slate-300 p-1.5 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            <GitCommitHorizontal size={18} />
          </button>
        )}
      </div>
      <div
        className="min-h-0 flex-1 overflow-auto flex flex-col"
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
        <BlockNoteView editor={editor} editable={!readOnly} slashMenu={false} formattingToolbar={false} theme={dark ? "dark" : "light"}>
          <FormattingToolbarController formattingToolbar={CustomFormattingToolbar} />
          {!readOnly && (
            <SuggestionMenuController
              triggerCharacter="/"
              getItems={async (query) => {
                const defaults = getDefaultReactSlashMenuItems(editor);
                const chemItem = {
                  title: "Chemical Structure",
                  subtext: "Draw a molecule or reaction",
                  aliases: ["molecule", "structure", "chem", "mol", "ketcher"],
                  group: "Chemistry",
                  icon: <FlaskConical size={18} />,
                  onItemClick: () => {
                    const current = editor.getTextCursorPosition().block;
                    editor.insertBlocks(
                      [{ type: "chemStructure" as any }],
                      current,
                      "after",
                    );
                  },
                };
                const all = [...defaults, chemItem];
                if (!query) return all;
                const q = query.toLowerCase();
                return all.filter(
                  (item) =>
                    item.title.toLowerCase().includes(q) ||
                    item.aliases?.some((a) => a.toLowerCase().includes(q)),
                );
              }}
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

      {/* Ketcher modal — lazy-loaded on first open */}
      <KetcherModal
        open={ketcher.open}
        initialKet={ketcher.ket}
        onSave={handleKetcherSave}
        onClose={handleKetcherClose}
      />
    </div>
  );
}
