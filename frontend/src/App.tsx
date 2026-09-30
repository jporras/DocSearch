import { FormEvent, useEffect, useState } from "react";
import {
  DocumentDetail,
  DocumentStatus,
  BatchAccepted,
  BatchItem,
  SearchResponse,
  getDocument,
  searchDocuments,
  subscribeToDocument,
  uploadBatch,
} from "./api";

type Screen = "search" | "upload";

function StatusPill({ status }: { status: BatchItem["status"] }) {
  return <span className={`status status--${status.toLowerCase()}`}>{status}</span>;
}

function HighlightedText({ text }: { text: string }) {
  let highlighted = false;
  return (
    <p className="headline">
      {text.split(/(<mark>|<\/mark>)/).map((part, index) => {
        if (part === "<mark>") { highlighted = true; return null; }
        if (part === "</mark>") { highlighted = false; return null; }
        return highlighted ? <mark key={index}>{part}</mark> : part;
      })}
    </p>
  );
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("search");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [selected, setSelected] = useState<DocumentDetail | null>(null);
  const [uploadResult, setUploadResult] = useState<BatchAccepted | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!uploadResult) return;
    const sources = uploadResult.items
      .filter((item) => item.id && item.status === "PROCESSING")
      .map((item) => subscribeToDocument(
        item.id as string,
        (nextStatus) => setUploadResult((current) => current ? {
          ...current,
          items: current.items.map((currentItem) => currentItem.id === nextStatus.id
            ? { ...currentItem, ...nextStatus } as BatchItem
            : currentItem),
        } : current),
        () => setError("Se perdió una conexión de eventos; el navegador intentará reconectarse."),
      ));
    return () => sources.forEach((source) => source.close());
  }, [uploadResult?.items.map((item) => `${item.id}:${item.status}`).join("|")]);

  async function runSearch(page = 1) {
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    try {
      setResults(await searchDocuments(query.trim(), page));
      setSelected(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No fue posible buscar.");
    } finally {
      setLoading(false);
    }
  }

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    await runSearch();
  }

  async function openDocument(id: string) {
    setLoading(true);
    setError("");
    try {
      setSelected(await getDocument(id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No fue posible abrir el documento.");
    } finally {
      setLoading(false);
    }
  }

  async function onUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const source = new FormData(event.currentTarget);
      const files = source.getAll("files").filter((value): value is File => value instanceof File && value.size > 0);
      const rawTags = String(source.get("tags") ?? "");
      const common = {
        author: String(source.get("author") ?? ""),
        category: String(source.get("category") ?? ""),
        tags: rawTags.split(",").map((tag) => tag.trim()).filter(Boolean),
        version: String(source.get("version") ?? ""),
      };
      const baseTitle = String(source.get("title") ?? "");
      const payload = new FormData();
      files.forEach((file) => payload.append("files", file));
      payload.set("metadata_json", JSON.stringify(files.map((file) => ({
        ...common,
        title: files.length === 1
          ? baseTitle
          : `${baseTitle} — ${file.name.replace(/\.[^.]+$/, "")}`,
      }))));
      setUploadResult(await uploadBatch(payload));
      event.currentTarget.reset();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No fue posible cargar el documento.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <span className="eyebrow">Davivienda · prueba técnica</span>
          <h1>Atlas Docs</h1>
          <p className="sidebar-copy">Documentación técnica, indexada y disponible en segundos.</p>
        </div>
        <nav aria-label="Navegación principal">
          <button className={screen === "search" ? "active" : ""} onClick={() => setScreen("search")}>⌕ Buscar</button>
          <button className={screen === "upload" ? "active" : ""} onClick={() => setScreen("upload")}>＋ Cargar</button>
        </nav>
        <div className="system-note"><span className="live-dot" /> PostgreSQL FTS + SSE</div>
      </aside>

      <main>
        {error && <div className="alert" role="alert">{error}</div>}

        {screen === "search" ? (
          <section>
            <header className="page-header">
              <span className="eyebrow">Biblioteca técnica</span>
              <h2>Encuentra la respuesta exacta.</h2>
              <p>Busca en títulos, metadatos y contenido completo con relevancia y resaltado.</p>
            </header>
            <form className="search-box" onSubmit={onSearch}>
              <input aria-label="Términos de búsqueda" value={query} onChange={(e) => setQuery(e.target.value)} placeholder='Ej. "arquitectura de pagos" redis' />
              <button disabled={loading || !query.trim()}>{loading ? "Buscando…" : "Buscar"}</button>
            </form>

            {results && !selected && (
              <div className="results">
                <div className="results-meta"><strong>{results.total} resultados</strong><span>{results.elapsed_ms} ms · página {results.page} de {results.total_pages || 1}</span></div>
                {results.items.length === 0 ? <div className="empty">No encontramos coincidencias. Prueba con otros términos.</div> : results.items.map((item) => (
                  <article className="result-card" key={item.id} onClick={() => openDocument(item.id)}>
                    <div className="result-top"><span className="file-kind">{item.filename.split(".").pop()?.toUpperCase()}</span><span>{item.category} · v{item.version}</span></div>
                    <h3>{item.title}</h3>
                    <HighlightedText text={item.headline} />
                    <div className="tags">{item.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
                    <small>Por {item.author}</small>
                  </article>
                ))}
                {results.total_pages > 1 && <div className="pagination">
                  <button disabled={results.page === 1} onClick={() => runSearch(results.page - 1)}>Anterior</button>
                  <button disabled={results.page === results.total_pages} onClick={() => runSearch(results.page + 1)}>Siguiente</button>
                </div>}
              </div>
            )}

            {selected && (
              <article className="viewer">
                <button className="back" onClick={() => setSelected(null)}>← Volver a resultados</button>
                <div className="viewer-header"><div><span className="eyebrow">{selected.category}</span><h2>{selected.title}</h2></div><span className="file-kind">{selected.filename.split(".").pop()?.toUpperCase()}</span></div>
                <dl><div><dt>Autor</dt><dd>{selected.author}</dd></div><div><dt>Versión</dt><dd>{selected.version}</dd></div><div><dt>Archivo</dt><dd>{selected.filename}</dd></div><div><dt>Tamaño</dt><dd>{Math.ceil(selected.size_bytes / 1024)} KB</dd></div></dl>
                <div className="tags">{selected.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
                <pre className="document-body">{selected.content}</pre>
              </article>
            )}
          </section>
        ) : (
          <section className="upload-section">
            <header className="page-header"><span className="eyebrow">Nueva fuente</span><h2>Publica documentación.</h2><p>La respuesta es inmediata; el procesamiento ocurre en segundo plano.</p></header>
            <form className="upload-form" onSubmit={onUpload}>
              <label className="file-drop"><strong>Selecciona uno o varios documentos</strong><span>TXT, Markdown o PDF · máximo 10 MB por archivo</span><input name="files" type="file" accept=".txt,.md,.pdf" multiple required /></label>
              <div className="form-grid"><label>Título base<input name="title" required maxLength={180} /></label><label>Autor<input name="author" required maxLength={150} /></label><label>Categoría<input name="category" required maxLength={100} /></label><label>Versión<input name="version" required maxLength={50} placeholder="1.0" /></label></div>
              <label>Etiquetas <span className="hint">separadas por coma</span><input name="tags" placeholder="backend, seguridad, pagos" /></label>
              <button className="primary" disabled={loading}>{loading ? "Enviando…" : "Cargar e indexar"}</button>
            </form>
            {uploadResult && <div>
              <p className="results-meta"><strong>{uploadResult.accepted} de {uploadResult.total} aceptados</strong><span>Lote {uploadResult.batch_id.slice(0, 8)}</span></p>
              {uploadResult.items.map((item, index) => <div className="processing-card" key={item.id ?? `${item.filename}-${index}`}><div><span className="eyebrow">Estado en tiempo real</span><h3>{item.title || item.filename}</h3><small>{item.filename}</small></div><StatusPill status={item.status} />{item.error && <p>{item.error}</p>}</div>)}
            </div>}
          </section>
        )}
      </main>
    </div>
  );
}
