import React, { useState, useEffect, useCallback } from "react";
import { InfoTip } from "../Tooltip";
import { AdminMobileRow } from "./AdminMobileRow";
import type { Rate, RateUpdate } from "../../types";
import { adminApi } from "../../api/admin";

interface RateFormData {
  season: Rate["season"];
  nightly_rate: number;
  daily_rate: number;
  effective_date: string;
}

interface RateModalProps {
  rate?: Rate | null;
  onClose: () => void;
  onSave: (id: number | null, data: RateFormData) => Promise<void>;
}

function RateModal({ rate, onClose, onSave }: RateModalProps) {
  const [formData, setFormData] = useState<RateFormData>({
    season: rate?.season || "offseason",
    nightly_rate: rate?.nightly_rate || 100,
    daily_rate: rate?.daily_rate || 50,
    effective_date: rate?.effective_date || new Date().toISOString().split("T")[0] || "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      await onSave(rate?.id || null, formData);
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
        <h3>{rate ? "Edit Rate" : "New Rate"}</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Season <InfoTip text="Jun–Sep is onseason, Oct–May is offseason" /></label>
            <select
              className="form-input"
              value={formData.season}
              onChange={(e) => setFormData({ ...formData, season: e.target.value as "offseason" | "onseason" })}
            >
              <option value="offseason">Offseason</option>
              <option value="onseason">Onseason</option>
            </select>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Nightly Rate ($)</label>
              <input
                type="number"
                className="form-input"
                value={formData.nightly_rate}
                onChange={(e) => setFormData({ ...formData, nightly_rate: parseFloat(e.target.value) })}
                min={0}
                step={0.01}
                required
              />
            </div>
            <div className="form-group">
              <label>Daily Rate ($)</label>
              <input
                type="number"
                className="form-input"
                value={formData.daily_rate}
                onChange={(e) => setFormData({ ...formData, daily_rate: parseFloat(e.target.value) })}
                min={0}
                step={0.01}
                required
              />
            </div>
          </div>
          <div className="form-group">
            <label>Effective Date <InfoTip text="Date when this rate takes effect" /></label>
            <input
              type="date"
              className="form-input"
              value={formData.effective_date}
              onChange={(e) => setFormData({ ...formData, effective_date: e.target.value })}
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

export function RatesAdmin() {
  const [rates, setRates] = useState<Rate[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingRate, setEditingRate] = useState<Rate | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);

  const fetchRates = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await adminApi.rates(signal);
      if (!signal?.aborted) setRates(data);
    } catch (err) {
      if (!signal?.aborted) console.error("Failed to fetch rates:", err);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void fetchRates(controller.signal);
    return () => controller.abort();
  }, [fetchRates]);

  const handleSave = async (rateId: number | null, data: RateFormData) => {
    if (rateId) {
      const update: RateUpdate = {
        season: data.season,
        nightly_rate: data.nightly_rate,
        daily_rate: data.daily_rate,
        effective_date: data.effective_date,
      };

      await adminApi.updateRate(rateId, update);
    } else {
      await adminApi.createRate(data);
    }
    await fetchRates();
  };

  const handleDelete = async (rateId: number) => {
    if (!confirm("Are you sure you want to delete this rate?")) return;

    setDeleting(rateId);
    try {
      await adminApi.deleteRate(rateId);
      await fetchRates();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete rate");
    } finally {
      setDeleting(null);
    }
  };

  const renderRateActions = (rate: Rate) => (
    <>
      <button className="action-btn edit-btn" onClick={() => setEditingRate(rate)}>
        Edit
      </button>
      <button
        className="action-btn delete-btn"
        onClick={() => handleDelete(rate.id)}
        disabled={deleting === rate.id}
      >
        {deleting === rate.id ? "..." : "Delete"}
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
        <h2>Rates</h2>
        <button className="add-btn" onClick={() => setShowCreateModal(true)}>
          + Add Rate
        </button>
      </div>
      <div className="admin-desktop-only admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Season</th>
                <th>Nightly Rate</th>
                <th>Daily Rate</th>
                <th>Effective Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rates.map((rate) => (
                <tr key={rate.id}>
                  <td>
                    <span className={`badge badge-${rate.season}`}>
                      {rate.season}
                    </span>
                  </td>
                  <td>${rate.nightly_rate.toFixed(2)}</td>
                  <td>${rate.daily_rate.toFixed(2)}</td>
                  <td>{rate.effective_date}</td>
                  <td className="actions-cell">
                    {renderRateActions(rate)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
      </div>
      <div className="admin-mobile-only">
        <div className="admin-mobile-compact-list">
          {rates.map((rate) => (
            <AdminMobileRow
              key={rate.id}
              eyebrow={rate.effective_date}
              badge={<span className={`badge badge-${rate.season}`}>{rate.season}</span>}
              title={`$${rate.nightly_rate.toFixed(2)} nightly`}
              meta={[`$${rate.daily_rate.toFixed(2)} daily`]}
              actions={renderRateActions(rate)}
            />
          ))}
        </div>
      </div>
      {(editingRate || showCreateModal) && (
        <RateModal
          rate={editingRate}
          onClose={() => {
            setEditingRate(null);
            setShowCreateModal(false);
          }}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
