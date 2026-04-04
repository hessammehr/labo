export type Notebook = {
  id: string;
  author_id: string;
  title: string;
  description: string;
  position: number;
  created_at: string;
  updated_at: string;
  sharing_level: string | null;
};

export type Entry = {
  id: string;
  notebook_id: string;
  author_id: string;
  title: string;
  content_blocks: Array<Record<string, unknown>>;
  tags: string[];
  version: number;
  position: number;
  created_at: string;
  updated_at: string;
};

export type Attachment = {
  id: string;
  entry_id: string;
  type: "image" | "excel" | "file";
  filename: string;
  mime_type: string;
  size: number;
  storage_uri: string;
  created_at: string;
};

export type PermissionDetail = {
  id: number;
  subject_id: string;
  subject_name: string;
  subject_email: string;
  resource_type: string;
  resource_id: string;
  access_level: "read" | "write" | "owner";
  created_at: string;
};

export type UserSearchResult = {
  id: string;
  name: string;
  email: string;
};

export type ScopedToken = {
  id: string;
  token_prefix: string;
  label: string;
  resource_type: string;
  resource_id: string;
  access_level: "read" | "readwrite";
  created_at: string;
  last_used_at: string | null;
};

export type ScopedTokenCreated = ScopedToken & {
  token: string;
};

export type SearchResult = {
  type: "notebook" | "entry";
  id: string;
  title: string;
  notebook_id: string | null;
  notebook_title: string | null;
  snippet: string;
  score: number;
};
