export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export type DocumentStatus = {
  id: string;
  filename: string;
  title: string;
  status: "PROCESSING" | "INDEXED" | "ERROR";
  error?: string | null;
  created_at: string;
  updated_at: string;
  correlation_id: string;
  batch_id: string | null;
};

export type DocumentAccepted = DocumentStatus & {
  message: string;
};

export type BatchItem = {
  id?: string | null;
  filename: string;
  title: string;
  status: "PROCESSING" | "REJECTED" | "ERROR" | "INDEXED";
  correlation_id?: string | null;
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type BatchAccepted = {
  batch_id: string;
  total: number;
  accepted: number;
  rejected: number;
  items: BatchItem[];
};

export type SearchItem = {
  id: string;
  filename: string;
  title: string;
  author: string;
  category: string;
  tags: string[];
  version: string;
  headline: string;
  rank: number;
  indexed_at: string | null;
};

export type SearchResponse = {
  items: SearchItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  elapsed_ms: number;
};

export type DocumentDetail = SearchItem & {
  content_type: string;
  size_bytes: number;
  status: string;
  content: string;
  created_at: string;
};

async function json<T>(response: Response): Promise<T> {
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail ?? payload.message ?? "La solicitud no pudo completarse.");
  }
  return payload as T;
}

export async function uploadDocument(form: FormData): Promise<DocumentAccepted> {
  return json(await fetch(`${API_BASE}/api/documents`, { method: "POST", body: form }));
}

export async function uploadBatch(form: FormData): Promise<BatchAccepted> {
  return json(await fetch(`${API_BASE}/api/documents/batch`, { method: "POST", body: form }));
}

export async function searchDocuments(query: string, page = 1): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, page: String(page), page_size: "10" });
  return json(await fetch(`${API_BASE}/api/documents/search?${params}`));
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  return json(await fetch(`${API_BASE}/api/documents/${id}`));
}

export function subscribeToDocument(
  id: string,
  onStatus: (status: DocumentStatus) => void,
  onConnectionError: () => void,
): EventSource {
  const source = new EventSource(`${API_BASE}/api/documents/${id}/events`);
  for (const eventName of ["snapshot", "document_status"]) {
    source.addEventListener(eventName, (event) => {
      const status = JSON.parse((event as MessageEvent).data) as DocumentStatus;
      onStatus(status);
      if (status.status === "INDEXED" || status.status === "ERROR") source.close();
    });
  }
  source.onerror = onConnectionError;
  return source;
}
