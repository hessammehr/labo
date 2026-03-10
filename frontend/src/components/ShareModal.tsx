import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Pencil, Shield, Trash2, X } from "lucide-react";

import { api } from "../lib/api";
import type { PermissionDetail, UserSearchResult } from "../lib/types";

type AccessLevel = "read" | "write" | "owner";

const LEVEL_LABELS: Record<AccessLevel, string> = {
  read: "Viewer",
  write: "Editor",
  owner: "Owner",
};

const LEVEL_ICONS: Record<AccessLevel, typeof Eye> = {
  read: Eye,
  write: Pencil,
  owner: Shield,
};

export function ShareModal({
  resourceId,
  resourceName,
  onClose,
}: {
  resourceId: string;
  resourceName: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const backdropRef = useRef<HTMLDivElement>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedLevel, setSelectedLevel] = useState<AccessLevel>("read");

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Fetch current permissions
  const permissionsQuery = useQuery({
    queryKey: ["permissions", "notebook", resourceId],
    queryFn: async () => {
      const { data } = await api.get<PermissionDetail[]>(
        `/permissions/resource/notebook/${resourceId}`
      );
      return data;
    },
  });

  // Search users
  const searchUsersQuery = useQuery({
    queryKey: ["users-search", searchQuery],
    queryFn: async () => {
      const { data } = await api.get<UserSearchResult[]>(
        `/permissions/users/search`,
        { params: { q: searchQuery } }
      );
      return data;
    },
    enabled: searchQuery.length >= 1,
  });

  const grantPermission = useMutation({
    mutationFn: async ({
      subjectId,
      accessLevel,
    }: {
      subjectId: string;
      accessLevel: AccessLevel;
    }) => {
      await api.post("/permissions/", {
        subject_id: subjectId,
        resource_type: "notebook",
        resource_id: resourceId,
        access_level: accessLevel,
      });
    },
    onSuccess: async () => {
      setSearchQuery("");
      await queryClient.invalidateQueries({
        queryKey: ["permissions", "notebook", resourceId],
      });
      // Refresh tree data so sharing icons update
      await queryClient.invalidateQueries({ queryKey: ["notebooks"] });
      await queryClient.invalidateQueries({ queryKey: ["entries"] });
    },
  });

  const updatePermission = useMutation({
    mutationFn: async ({
      subjectId,
      accessLevel,
    }: {
      subjectId: string;
      accessLevel: AccessLevel;
    }) => {
      await api.post("/permissions/", {
        subject_id: subjectId,
        resource_type: "notebook",
        resource_id: resourceId,
        access_level: accessLevel,
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["permissions", "notebook", resourceId],
      });
      await queryClient.invalidateQueries({ queryKey: ["notebooks"] });
      await queryClient.invalidateQueries({ queryKey: ["entries"] });
    },
  });

  const revokePermission = useMutation({
    mutationFn: async (permissionId: number) => {
      await api.delete(`/permissions/${permissionId}`);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["permissions", "notebook", resourceId],
      });
      await queryClient.invalidateQueries({ queryKey: ["notebooks"] });
      await queryClient.invalidateQueries({ queryKey: ["entries"] });
    },
  });

  const permissions = permissionsQuery.data ?? [];
  const existingSubjectIds = new Set(permissions.map((p) => p.subject_id));
  const searchResults = (searchUsersQuery.data ?? []).filter(
    (u) => !existingSubjectIds.has(u.id)
  );
  const isLastOwner = permissions.filter((p) => p.access_level === "owner").length <= 1;

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
              Share Notebook
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

        {/* Add people */}
        <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800">
          <div className="flex gap-2">
            <input
              autoFocus
              type="text"
              placeholder="Search by name or email…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-2.5 py-1.5 text-sm outline-none focus:border-blue-500 dark:text-slate-100"
            />
            <select
              value={selectedLevel}
              onChange={(e) => setSelectedLevel(e.target.value as AccessLevel)}
              className="rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-2 py-1.5 text-sm dark:text-slate-100"
            >
              <option value="read">Viewer</option>
              <option value="write">Editor</option>
              <option value="owner">Owner</option>
            </select>
          </div>

          {/* Search results dropdown */}
          {searchQuery.length >= 1 && searchResults.length > 0 && (
            <div className="mt-1 max-h-32 overflow-y-auto rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
              {searchResults.map((u) => (
                <button
                  key={u.id}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
                  onClick={() =>
                    grantPermission.mutate({
                      subjectId: u.id,
                      accessLevel: selectedLevel,
                    })
                  }
                >
                  <div className="flex-1 min-w-0">
                    <div className="truncate text-slate-900 dark:text-slate-100">
                      {u.name}
                    </div>
                    <div className="truncate text-xs text-slate-500 dark:text-slate-400">
                      {u.email}
                    </div>
                  </div>
                  <span className="shrink-0 text-xs text-slate-400">
                    Add as {LEVEL_LABELS[selectedLevel]}
                  </span>
                </button>
              ))}
            </div>
          )}

          {searchQuery.length >= 1 &&
            searchResults.length === 0 &&
            !searchUsersQuery.isLoading && (
              <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 px-1">
                No users found
              </p>
            )}
        </div>

        {/* Current permissions list */}
        <div className="px-4 py-3 max-h-64 overflow-y-auto">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
            People with access
          </div>

          {permissionsQuery.isLoading && (
            <p className="text-xs text-slate-400">Loading…</p>
          )}

          {permissions.length === 0 && !permissionsQuery.isLoading && (
            <p className="text-xs text-slate-400">No permissions set</p>
          )}

          {permissions.map((perm) => {
            const Icon = LEVEL_ICONS[perm.access_level as AccessLevel] ?? Eye;
            const canRemove =
              !(perm.access_level === "owner" && isLastOwner);
            return (
              <div
                key={perm.id}
                className="flex items-center gap-2 py-1.5 group"
              >
                <Icon
                  size={14}
                  className="shrink-0 text-slate-400 dark:text-slate-500"
                />
                <div className="flex-1 min-w-0">
                  <div className="truncate text-sm text-slate-900 dark:text-slate-100">
                    {perm.subject_name}
                  </div>
                  <div className="truncate text-xs text-slate-500 dark:text-slate-400">
                    {perm.subject_email}
                  </div>
                </div>
                <select
                  value={perm.access_level}
                  onChange={(e) =>
                    updatePermission.mutate({
                      subjectId: perm.subject_id,
                      accessLevel: e.target.value as AccessLevel,
                    })
                  }
                  className="rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-1.5 py-0.5 text-xs dark:text-slate-100"
                >
                  <option value="read">Viewer</option>
                  <option value="write">Editor</option>
                  <option value="owner">Owner</option>
                </select>
                <button
                  title={
                    canRemove
                      ? "Remove access"
                      : "Cannot remove the last owner"
                  }
                  disabled={!canRemove}
                  className="p-1 text-slate-400 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed opacity-0 group-hover:opacity-100"
                  onClick={() => revokePermission.mutate(perm.id)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            );
          })}
        </div>

        {/* Footer note about cascading */}
        {(
          <div className="border-t border-slate-200 dark:border-slate-800 px-4 py-2">
            <p className="text-[11px] text-slate-400 dark:text-slate-500">
              Notebook permissions apply to all entries and attachments within.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
