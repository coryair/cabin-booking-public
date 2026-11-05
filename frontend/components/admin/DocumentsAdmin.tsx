import React, { useState, useEffect, useCallback } from "react";
import { AdminMobileRow } from "./AdminMobileRow";
import type { Document } from "../../types";
import { adminApi } from "../../api/admin";

interface DocumentFormData {
  title: string;
  url: string;
  description: string;
}

interface DocumentModalProps {
  doc?: Document | null;
  onClose: () => void;
  onSave: (id: number | null, data: DocumentFormData) => Promise<void>;
}

function DocumentModal({ doc, onClose, onSave }: DocumentModalProps) {
  const [formData, setFormData] = useState<DocumentFormData>({
    title: doc?.title || "",
    url: doc?.url || "",
    description: doc?.description || "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      await onSave(doc?.id ?? null, formData);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal admin-modal" onClick={(e) => e.stopPropagation()}>
        <h3>{doc ? "Edit Document" : "New Document"}</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Title</label>
            <input
              type="text"
              className="form-input"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              required
              placeholder="e.g., Cabin Rules & Guidelines"
            />
          </div>
          <div className="form-group">
            <label>URL</label>
            <input
              type="url"
              className="form-input"
              value={formData.url}
              onChange={(e) => setFormData({ ...formData, url: e.target.value })}
              required
              placeholder="https://docs.google.com/..."
            />
          </div>
          <div className="form-group">
            <label>Description</label>
            <textarea
              className="form-input form-textarea"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={2}
              placeholder="Brief description shown on the Guide page"
            />
          </div>
          {error && <div className="modal-error">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="cancel-btn" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="confirm-btn" disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function DocumentsAdmin() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingDoc, setEditingDoc] = useState<Document | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);

  const fetchDocuments = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await adminApi.documents(signal);
      if (!signal?.aborted) setDocuments(data);
    } catch (err) {
      if (!signal?.aborted) console.error("Failed to fetch documents:", err);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void fetchDocuments(controller.signal);
    return () => controller.abort();
  }, [fetchDocuments]);

  const handleSave = async (
    id: number | null,
    data: DocumentFormData,
  ) => {
    if (id !== null) {
      await adminApi.updateDocument(id, data);
    } else {
      await adminApi.createDocument(data);
    }
    await fetchDocuments();
  };

  const handleDelete = async (id: number) => {
    const doc = documents.find((d) => d.id === id);
    if (!confirm(`Delete "${doc?.title}"?`)) return;

    setDeleting(id);
    try {
      await adminApi.deleteDocument(id);
      await fetchDocuments();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete document");
    } finally {
      setDeleting(null);
    }
  };

  const renderDocActions = (doc: Document) => (
    <>
      <button className="action-btn edit-btn" onClick={() => setEditingDoc(doc)}>
        Edit
      </button>
      <button
        className="action-btn delete-btn"
        onClick={() => handleDelete(doc.id)}
        disabled={deleting === doc.id}
      >
        {deleting === doc.id ? "..." : "Delete"}
      </button>
    </>
  );

  if (loading) {
    return (
      <div className="admin-loading">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Documents</h2>
        <button className="add-btn" onClick={() => setShowCreateModal(true)}>
          + Add Document
        </button>
      </div>
      <div className="admin-desktop-only admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>URL</th>
                <th>Description</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.length === 0 ? (
                <tr>
                  <td colSpan={4} style={{ textAlign: "center", opacity: 0.5 }}>
                    No documents yet
                  </td>
                </tr>
              ) : (
                documents.map((doc) => (
                  <tr key={doc.id}>
                    <td>{doc.title}</td>
                    <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      <a href={doc.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--selected-color)" }}>
                        {doc.url}
                      </a>
                    </td>
                    <td>{doc.description || "-"}</td>
                    <td className="actions-cell">
                      {renderDocActions(doc)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
      </div>
      <div className="admin-mobile-only">
        {documents.length === 0 ? (
          <div className="admin-mobile-empty">No documents yet</div>
        ) : (
          <div className="admin-mobile-compact-list">
            {documents.map((doc) => (
              <AdminMobileRow
                key={doc.id}
                eyebrow="Document"
                title={doc.title}
                meta={[
                  <a className="admin-mobile-link" href={doc.url} target="_blank" rel="noopener noreferrer">{doc.url}</a>,
                  doc.description || "No description",
                ]}
                actions={renderDocActions(doc)}
              />
            ))}
          </div>
        )}
      </div>
      {(editingDoc || showCreateModal) && (
        <DocumentModal
          doc={editingDoc}
          onClose={() => {
            setEditingDoc(null);
            setShowCreateModal(false);
          }}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
