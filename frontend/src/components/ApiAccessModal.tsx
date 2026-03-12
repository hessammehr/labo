import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ClipboardCopy, Key, Plus, Trash2, X } from "lucide-react";

import { api } from "../lib/api";
import type { ScopedToken, ScopedTokenCreated } from "../lib/types";

type TokenAccessLevel = "read" | "readwrite";
type SnippetLang = "python" | "javascript" | "curl";

function generateSnippet(
  lang: SnippetLang,
  baseUrl: string,
  token: string,
  resourceType: string,
): string {
  const examplePath =
    resourceType === "notebook" ? "My Entry/data.csv" : "data.csv";

  if (lang === "python") {
    return `from labo import Resource

r = Resource("${baseUrl}", "${token}")
data = (r / "${examplePath}").read_text()
`;
  }

  if (lang === "javascript") {
    const urlPath = `${baseUrl}/api/v1/files/${examplePath}`;
    return `const res = await fetch("${urlPath}", {
  headers: { Authorization: "Bearer ${token}" },
});
const data = await res.text();
`;
  }

  const urlPath = `${baseUrl}/api/v1/files/${examplePath}`;
  return `curl -H "Authorization: Bearer ${token}" "${urlPath}"
`;
}

export function ApiAccessModal({
  resourceId,
  resourceType,
  resourceName,
  onClose,
}: {
  resourceId: string;
  resourceType: "notebook" | "entry";
  resourceName: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const backdropRef = useRef<HTMLDivElement>(null);
  const [newTokenLevel, setNewTokenLevel] = useState<TokenAccessLevel>("read");
  const [newTokenLabel, setNewTokenLabel] = useState("");
  const [justCreatedToken, setJustCreatedToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [snippetLang, setSnippetLang] = useState<SnippetLang>("python");

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const tokensQuery = useQuery({
    queryKey: ["scoped-tokens", resourceType, resourceId],
    queryFn: async () => {
      const { data } = await api.get<ScopedToken[]>(
        `/scoped-tokens/resource/${resourceType}/${resourceId}`
      );
      return data;
    },
  });

  const createToken = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<ScopedTokenCreated>("/scoped-tokens/", {
        resource_type: resourceType,
        resource_id: resourceId,
        access_level: newTokenLevel,
        label: newTokenLabel || "Untitled token",
      });
      return data;
    },
    onSuccess: async (data) => {
      setJustCreatedToken(data.token);
      setNewTokenLabel("");
      setCopied(false);
      await queryClient.invalidateQueries({
        queryKey: ["scoped-tokens", resourceType, resourceId],
      });
    },
  });

  const updateToken = useMutation({
    mutationFn: async ({
      tokenId,
      accessLevel,
    }: {
      tokenId: string;
      accessLevel: TokenAccessLevel;
    }) => {
      await api.patch(`/scoped-tokens/${tokenId}`, {
        access_level: accessLevel,
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["scoped-tokens", resourceType, resourceId],
      });
    },
  });

  const revokeToken = useMutation({
    mutationFn: async (tokenId: string) => {
      await api.delete(`/scoped-tokens/${tokenId}`);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["scoped-tokens", resourceType, resourceId],
      });
    },
  });

  const tokens = tokensQuery.data ?? [];
  const baseUrl = window.location.origin;

  const copyToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === backdropRef.current) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              API Access
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 truncate">
              {resourceName}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded"
          >
            <X size={16} />
          </button>
        </div>

        {/* Create new token */}
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800">
          <div className="flex gap-2">
            <input
              autoFocus
              type="text"
              placeholder="Token label (optional)"
              value={newTokenLabel}
              onChange={(e) => setNewTokenLabel(e.target.value)}
              className="flex-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-2.5 py-1.5 text-sm outline-none focus:border-blue-500 dark:text-slate-100"
              onKeyDown={(e) => {
                if (e.key === "Enter") createToken.mutate();
              }}
            />
            <select
              value={newTokenLevel}
              onChange={(e) =>
                setNewTokenLevel(e.target.value as TokenAccessLevel)
              }
              className="rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-2 py-1.5 text-sm dark:text-slate-100"
            >
              <option value="read">Read</option>
              <option value="readwrite">Read + Write</option>
            </select>
            <button
              onClick={() => createToken.mutate()}
              disabled={createToken.isPending}
              className="flex items-center gap-1 rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <Plus size={14} /> Create
            </button>
          </div>

          {/* Just-created token (shown once) */}
          {justCreatedToken && (
            <div className="mt-2 rounded border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-950/40 p-2">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-medium text-green-800 dark:text-green-300">
                  Token created — copy it now, it won't be shown again
                </span>
                <button
                  onClick={() => copyToClipboard(justCreatedToken)}
                  className="flex items-center gap-1 text-xs text-green-700 dark:text-green-400 hover:underline"
                >
                  {copied ? <Check size={12} /> : <ClipboardCopy size={12} />}
                  {copied ? "Copied" : "Copy token"}
                </button>
              </div>
              <code className="block text-xs font-mono text-green-900 dark:text-green-200 bg-green-100 dark:bg-green-900/40 rounded px-2 py-1 break-all select-all">
                {justCreatedToken}
              </code>

              {/* Code snippet */}
              <div className="mt-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] font-medium text-green-700 dark:text-green-400">
                    Example usage
                  </span>
                  <select
                    value={snippetLang}
                    onChange={(e) =>
                      setSnippetLang(e.target.value as SnippetLang)
                    }
                    className="rounded border border-green-300 dark:border-green-700 bg-white dark:bg-green-950 px-1.5 py-0.5 text-[11px] text-green-800 dark:text-green-300"
                  >
                    <option value="python">Python</option>
                    <option value="javascript">JavaScript</option>
                    <option value="curl">curl</option>
                  </select>
                </div>
                <div className="relative">
                  <pre className="text-[11px] font-mono text-green-900 dark:text-green-200 bg-green-100 dark:bg-green-900/40 rounded px-2 py-1.5 overflow-x-auto whitespace-pre">
                    {generateSnippet(
                      snippetLang,
                      baseUrl,
                      justCreatedToken,
                      resourceType,
                    )}
                  </pre>
                  <button
                    onClick={() =>
                      copyToClipboard(
                        generateSnippet(
                          snippetLang,
                          baseUrl,
                          justCreatedToken,
                          resourceType,
                        )
                      )
                    }
                    className="absolute top-1 right-1 p-0.5 text-green-600 dark:text-green-400 hover:text-green-800"
                    title="Copy snippet"
                  >
                    <ClipboardCopy size={11} />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Existing tokens list */}
        <div className="px-4 py-3 max-h-64 overflow-y-auto">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
            Active tokens
          </div>

          {tokensQuery.isLoading && (
            <p className="text-xs text-slate-400">Loading…</p>
          )}

          {tokens.length === 0 && !tokensQuery.isLoading && (
            <p className="text-xs text-slate-400">
              No API tokens. Create one above to enable programmatic access.
            </p>
          )}

          {tokens.map((tok) => (
            <div
              key={tok.id}
              className="flex items-center gap-2 py-1.5 group"
            >
              <Key
                size={14}
                className="shrink-0 text-slate-400 dark:text-slate-500"
              />
              <div className="flex-1 min-w-0">
                <div className="truncate text-sm text-slate-900 dark:text-slate-100">
                  {tok.label || "Untitled"}
                </div>
                <div className="truncate text-xs text-slate-500 dark:text-slate-400">
                  {tok.token_prefix}… ·{" "}
                  {tok.last_used_at
                    ? `used ${new Date(tok.last_used_at).toLocaleDateString()}`
                    : "never used"}
                </div>
              </div>
              <select
                value={tok.access_level}
                onChange={(e) =>
                  updateToken.mutate({
                    tokenId: tok.id,
                    accessLevel: e.target.value as TokenAccessLevel,
                  })
                }
                className="rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-1.5 py-0.5 text-xs dark:text-slate-100"
              >
                <option value="read">Read</option>
                <option value="readwrite">Read + Write</option>
              </select>
              <button
                title="Revoke token"
                className="p-1 text-slate-400 hover:text-red-600 opacity-0 group-hover:opacity-100"
                onClick={() => revokeToken.mutate(tok.id)}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-200 dark:border-slate-800 px-4 py-2">
          <p className="text-[11px] text-slate-400 dark:text-slate-500">
            {resourceType === "notebook"
              ? "Tokens grant access to all entries and attachments in this notebook."
              : "Tokens grant access to all attachments in this entry."}
          </p>
        </div>
      </div>
    </div>
  );
}
