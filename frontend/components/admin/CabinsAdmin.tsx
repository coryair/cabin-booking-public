import React, { useState } from "react";
import { InfoTip } from "../Tooltip";
import { AdminMobileRow } from "./AdminMobileRow";
import type { Cabin, CabinUpdate } from "../../types";
import { adminApi } from "../../api/admin";
import { useAppData } from "../../context/AppDataContext";

interface CabinFormData {
  cabin_id: string;
  cabin_name: string;
  description: string;
  max_guests: number;
}

interface CabinModalProps {
  cabin?: Cabin | null;
  onClose: () => void;
  onSave: (cabinId: string | null, data: CabinFormData) => Promise<void>;
}

function CabinModal({ cabin, onClose, onSave }: CabinModalProps) {
  const [formData, setFormData] = useState<CabinFormData>({
    cabin_id: cabin?.cabin_id || "",
    cabin_name: cabin?.cabin_name || "",
    description: cabin?.description || "",
    max_guests: cabin?.max_guests || 10,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      await onSave(cabin?.cabin_id || null, formData);
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
        <h3>{cabin ? "Edit Cabin" : "New Cabin"}</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Cabin ID</label>
            <input
              type="text"
              className="form-input"
              value={formData.cabin_id}
              onChange={(e) => setFormData({ ...formData, cabin_id: e.target.value })}
              required
              disabled={!!cabin}
              placeholder="e.g., pine"
            />
          </div>
          <div className="form-group">
            <label>Display Name</label>
            <input
              type="text"
              className="form-input"
              value={formData.cabin_name}
              onChange={(e) => setFormData({ ...formData, cabin_name: e.target.value })}
              required
              placeholder="e.g., Pine"
            />
          </div>
          <div className="form-group">
            <label>Description</label>
            <textarea
              className="form-input form-textarea"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={3}
            />
          </div>
          <div className="form-group">
            <label>Max Guests <InfoTip text="Maximum guests this cabin can hold" /></label>
            <input
              type="number"
              className="form-input"
              value={formData.max_guests}
              onChange={(e) => setFormData({ ...formData, max_guests: parseInt(e.target.value) })}
              min={1}
              required
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

export function CabinsAdmin() {
  const {
    cabins,
    cabinsLoading: loading,
    cabinsError,
    refreshCabins,
  } = useAppData();
  const [editingCabin, setEditingCabin] = useState<Cabin | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const handleSave = async (cabinId: string | null, data: CabinFormData) => {
    if (cabinId) {
      const update: CabinUpdate = {
        cabin_name: data.cabin_name,
        description: data.description,
        max_guests: data.max_guests,
      };

      await adminApi.updateCabin(cabinId, update);
    } else {
      await adminApi.createCabin(data);
    }
    await refreshCabins();
  };

  const handleDelete = async (cabinId: string) => {
    const cabin = cabins.find((c) => c.cabin_id === cabinId);
    if (!confirm(`Are you sure you want to delete cabin "${cabin?.cabin_name || cabinId}"?`)) return;

    setDeleting(cabinId);
    try {
      await adminApi.deleteCabin(cabinId);
      await refreshCabins();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete cabin");
    } finally {
      setDeleting(null);
    }
  };

  const renderCabinActions = (cabin: Cabin) => (
    <>
      <button className="action-btn edit-btn" onClick={() => setEditingCabin(cabin)}>
        Edit
      </button>
      <button
        className="action-btn delete-btn"
        onClick={() => handleDelete(cabin.cabin_id)}
        disabled={deleting === cabin.cabin_id}
      >
        {deleting === cabin.cabin_id ? "..." : "Delete"}
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

  if (cabinsError) {
    return <div className="admin-error">{cabinsError}</div>;
  }

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Cabins</h2>
        <button className="add-btn" onClick={() => setShowCreateModal(true)}>
          + Add Cabin
        </button>
      </div>
      <div className="admin-desktop-only admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Description</th>
                <th>Max Guests</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {cabins.map((cabin) => (
                <tr key={cabin.cabin_id}>
                  <td className="cabin-id-cell">
                    <code>{cabin.cabin_id}</code>
                  </td>
                  <td className="cabin-name-cell">
                    <span className={`cabin-indicator ${cabin.cabin_id}`} />
                    {cabin.cabin_name}
                  </td>
                  <td>{cabin.description || "-"}</td>
                  <td>{cabin.max_guests}</td>
                  <td className="actions-cell">
                    {renderCabinActions(cabin)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
      </div>
      <div className="admin-mobile-only">
        <div className="admin-mobile-compact-list">
          {cabins.map((cabin) => (
            <AdminMobileRow
              key={cabin.cabin_id}
              eyebrow={cabin.cabin_id}
              badge={<code className="admin-mobile-code">{cabin.max_guests} max</code>}
              title={<><span className={`cabin-indicator ${cabin.cabin_id}`} />{cabin.cabin_name}</>}
              titleClassName="admin-mobile-cabin-title"
              meta={[cabin.description || "No description"]}
              actions={renderCabinActions(cabin)}
            />
          ))}
        </div>
      </div>
      {(editingCabin || showCreateModal) && (
        <CabinModal
          cabin={editingCabin}
          onClose={() => {
            setEditingCabin(null);
            setShowCreateModal(false);
          }}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
