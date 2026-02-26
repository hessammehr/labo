import { useEffect, useState } from "react";
import type { PartialBlock } from "@blocknote/core";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";

type EntryEditorFormProps = {
  initialTitle?: string;
  initialContent?: Array<Record<string, unknown>>;
  isSaving?: boolean;
  onSave: (payload: { title: string; content_blocks: Array<Record<string, unknown>> }) => Promise<void>;
};

export function EntryEditorForm({
  initialTitle = "",
  initialContent,
  isSaving = false,
  onSave,
}: EntryEditorFormProps) {
  const [title, setTitle] = useState(initialTitle);

  useEffect(() => {
    setTitle(initialTitle);
  }, [initialTitle]);

  const safeInitialContent =
    Array.isArray(initialContent) && initialContent.length > 0
      ? (initialContent as unknown as PartialBlock[])
      : undefined;

  const editor = useCreateBlockNote(
    safeInitialContent ? { initialContent: safeInitialContent } : {},
    [JSON.stringify(safeInitialContent ?? null)],
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-slate-200 px-4 py-2">
        <input
          className="w-full border border-slate-300 px-2 py-1 text-lg font-semibold outline-none"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Entry title"
        />
        <button
          onClick={() =>
            onSave({
              title,
              content_blocks: editor.document as unknown as Array<Record<string, unknown>>,
            })
          }
          disabled={isSaving}
          className="border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100 disabled:opacity-50"
        >
          {isSaving ? "Saving..." : "Save"}
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
        <BlockNoteView editor={editor} />
      </div>
    </div>
  );
}
