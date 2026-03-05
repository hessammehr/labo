export type Notebook = {
  id: string;
  owner_id: string;
  title: string;
  description: string;
  created_at: string;
  updated_at: string;
};

export type Entry = {
  id: string;
  notebook_id: string;
  author_id: string;
  title: string;
  content_blocks: Array<Record<string, unknown>>;
  tags: string[];
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
