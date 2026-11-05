import React, { useState, useEffect, useCallback } from "react";
import { InfoTip } from "../Tooltip";
import { AdminMobileRow } from "./AdminMobileRow";
import type { BookingSeason } from "../../types";
import { adminApi } from "../../api/admin";

const FIXED_PROCESSING_FEE_PCT = 0.04;
const FIXED_PROCESSING_FEE_LABEL = `${(FIXED_PROCESSING_FEE_PCT * 100).toFixed(0)}%`;

interface RoundFormData {
  round_number: number;
  start_date: string;
  end_date: string;
  window_days: number;
  max_reservations: number;
  max_nights: number | null;
  priority_order: string;
}

const DEFAULT_ROUNDS: RoundFormData[] = [
  { round_number: 1, start_date: "", end_date: "", window_days: 2, max_reservations: 2, max_nights: 10, priority_order: "priority" },
  { round_number: 2, start_date: "", end_date: "", window_days: 2, max_reservations: 1, max_nights: null, priority_order: "reverse" },
  { round_number: 3, start_date: "", end_date: "", window_days: 1, max_reservations: 1, max_nights: null, priority_order: "priority" },
];

function roundsFromSeason(season: BookingSeason): RoundFormData[] {
  if (season.rounds.length > 0) {
    return season.rounds.map((r) => ({
      round_number: r.round_number,
      start_date: r.start_date,
      end_date: r.end_date,
      window_days: r.window_days,
      max_reservations: r.max_reservations,
      max_nights: r.max_nights,
      priority_order: r.priority_order,
    }));
  }
  return DEFAULT_ROUNDS.map((round) => ({ ...round }));
}

interface SeasonFormData {
  year: number;
  prime_season_start: string;
  prime_season_end: string;
  open_season_start: string;
  open_season_end: string;
  season_max_nights: number;
  processing_fee_pct: number;
  guest_fee_per_day: number;
  rounds: RoundFormData[];
}

interface SeasonModalProps {
  season?: BookingSeason | null;
  onClose: () => void;
  onSave: (id: number | null, data: SeasonFormData) => Promise<void>;
}

function SeasonModal({ season, onClose, onSave }: SeasonModalProps) {
  const [formData, setFormData] = useState<SeasonFormData>({
    year: season?.year || new Date().getFullYear(),
    prime_season_start: season?.prime_season_start || "",
    prime_season_end: season?.prime_season_end || "",
    open_season_start: season?.open_season_start || "",
    open_season_end: season?.open_season_end || "",
    season_max_nights: season?.season_max_nights || 18,
    processing_fee_pct: FIXED_PROCESSING_FEE_PCT,
    guest_fee_per_day: season?.guest_fee_per_day ?? 10,
    rounds: season ? roundsFromSeason(season) : DEFAULT_ROUNDS.map((r) => ({ ...r })),
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      await onSave(season?.id || null, {
        ...formData,
        processing_fee_pct: FIXED_PROCESSING_FEE_PCT,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const setField = <Key extends keyof SeasonFormData>(key: Key, value: SeasonFormData[Key]) =>
    setFormData((prev) => ({ ...prev, [key]: value }));

  const setRoundField = <Key extends keyof RoundFormData>(
    index: number,
    key: Key,
    value: RoundFormData[Key],
  ) =>
    setFormData((prev) => ({
      ...prev,
      rounds: prev.rounds.map((r, i) => (i === index ? { ...r, [key]: value } : r)),
    }));

  const PRIORITY_LABELS: Record<string, string> = {
    priority: "Priority order",
    reverse: "Reverse priority order",
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal admin-modal season-modal" onClick={(e) => e.stopPropagation()}>
        <h3>{season ? `Edit ${season.year} Season` : "New Booking Season"}</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-group">
              <label>Year</label>
              <input type="number" className="form-input" value={formData.year}
                onChange={(e) => setField("year", parseInt(e.target.value))} required disabled={!!season} />
            </div>
            <div className="form-group">
              <label>Max Season Nights</label>
              <input type="number" className="form-input" value={formData.season_max_nights}
                onChange={(e) => setField("season_max_nights", parseInt(e.target.value))} min={1} required />
            </div>
            <div className="form-group">
              <label>Processing Fee % (Fixed)</label>
              <input
                type="text"
                className="form-input"
                value={FIXED_PROCESSING_FEE_LABEL}
                readOnly
                disabled
              />
            </div>
            <div className="form-group">
              <label>Guest Fee $/day</label>
              <input type="number" className="form-input" value={formData.guest_fee_per_day}
                onChange={(e) => setField("guest_fee_per_day", parseFloat(e.target.value))}
                min={0} step={0.5} required />
            </div>
          </div>

          <h4>Prime Season</h4>
          <div className="form-row">
            <div className="form-group">
              <label>Start</label>
              <input type="date" className="form-input" value={formData.prime_season_start}
                onChange={(e) => setField("prime_season_start", e.target.value)} required />
            </div>
            <div className="form-group">
              <label>End</label>
              <input type="date" className="form-input" value={formData.prime_season_end}
                onChange={(e) => setField("prime_season_end", e.target.value)} required />
            </div>
          </div>

          {formData.rounds.map((rnd, i) => (
            <React.Fragment key={rnd.round_number}>
              <h4>Round {rnd.round_number} <InfoTip text={`${PRIORITY_LABELS[rnd.priority_order] || rnd.priority_order}, ${rnd.window_days}-day windows`} /></h4>
              <div className="form-row">
                <div className="form-group">
                  <label>Start</label>
                  <input type="date" className="form-input" value={rnd.start_date}
                    onChange={(e) => setRoundField(i, "start_date", e.target.value)} required />
                </div>
                <div className="form-group">
                  <label>End</label>
                  <input type="date" className="form-input" value={rnd.end_date}
                    onChange={(e) => setRoundField(i, "end_date", e.target.value)} required />
                </div>
                <div className="form-group">
                  <label>Window Days</label>
                  <input type="number" className="form-input" value={rnd.window_days}
                    onChange={(e) => setRoundField(i, "window_days", parseInt(e.target.value))} min={1} required />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Max Reservations</label>
                  <input type="number" className="form-input" value={rnd.max_reservations}
                    onChange={(e) => setRoundField(i, "max_reservations", parseInt(e.target.value))} min={1} required />
                </div>
                <div className="form-group">
                  <label>Max Nights</label>
                  <input type="number" className="form-input" value={rnd.max_nights ?? ""}
                    onChange={(e) => setRoundField(i, "max_nights", e.target.value ? parseInt(e.target.value) : null)}
                    min={1} placeholder="No limit" />
                </div>
                <div className="form-group">
                  <label>Priority Order</label>
                  <select className="form-input" value={rnd.priority_order}
                    onChange={(e) => setRoundField(i, "priority_order", e.target.value)}>
                    <option value="priority">Priority</option>
                    <option value="reverse">Reverse</option>
                  </select>
                </div>
              </div>
            </React.Fragment>
          ))}

          <h4>Open Season</h4>
          <div className="form-row">
            <div className="form-group">
              <label>Start Date <InfoTip text="When unrestricted booking begins" /></label>
              <input type="date" className="form-input" value={formData.open_season_start}
                onChange={(e) => setField("open_season_start", e.target.value)} required />
            </div>
            <div className="form-group">
              <label>End Date <InfoTip text="When open booking ends (e.g. Labor Day)" /></label>
              <input type="date" className="form-input" value={formData.open_season_end}
                onChange={(e) => setField("open_season_end", e.target.value)} required />
            </div>
          </div>

          {error && <div className="modal-error">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="cancel-btn" onClick={onClose}>Cancel</button>
            <button type="submit" className="confirm-btn" disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function SeasonsAdmin() {
  const [seasons, setSeasons] = useState<BookingSeason[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingSeason, setEditingSeason] = useState<BookingSeason | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);

  const fetchSeasons = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await adminApi.seasons(signal);
      if (!signal?.aborted) setSeasons(data);
    } catch (err) {
      if (!signal?.aborted) console.error("Failed to fetch seasons:", err);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void fetchSeasons(controller.signal);
    return () => controller.abort();
  }, [fetchSeasons]);

  const handleSave = async (seasonId: number | null, data: SeasonFormData) => {
    if (seasonId) {
      await adminApi.updateSeason(seasonId, data);
    } else {
      await adminApi.createSeason(data);
    }
    await fetchSeasons();
  };

  const handleDelete = async (seasonId: number) => {
    if (!confirm("Are you sure you want to delete this season?")) return;

    setDeleting(seasonId);
    try {
      await adminApi.deleteSeason(seasonId);
      await fetchSeasons();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete season");
    } finally {
      setDeleting(null);
    }
  };

  const renderSeasonActions = (season: BookingSeason) => (
    <>
      <button className="action-btn edit-btn" onClick={() => setEditingSeason(season)}>
        Edit
      </button>
      <button
        className="action-btn delete-btn"
        onClick={() => handleDelete(season.id)}
        disabled={deleting === season.id}
      >
        {deleting === season.id ? "..." : "Delete"}
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
        <h2>Booking Seasons</h2>
        <button className="add-btn" onClick={() => setShowCreateModal(true)}>
          + Add Season
        </button>
      </div>
      <div className="admin-desktop-only admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Year</th>
                <th>Prime Season</th>
                <th>Round 1</th>
                <th>Round 2</th>
                <th>Round 3</th>
                <th>Open Season</th>
                <th>Max Nights</th>
                <th>Fee</th>
                <th>Guest Fee</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {seasons.map((s) => (
                <tr key={s.id}>
                  <td><strong>{s.year}</strong></td>
                  <td>{s.prime_season_start} &ndash; {s.prime_season_end}</td>
                  <td>{s.rounds[0]?.start_date ?? "–"} &ndash; {s.rounds[0]?.end_date ?? "–"}</td>
                  <td>{s.rounds[1]?.start_date ?? "–"} &ndash; {s.rounds[1]?.end_date ?? "–"}</td>
                  <td>{s.rounds[2]?.start_date ?? "–"} &ndash; {s.rounds[2]?.end_date ?? "–"}</td>
                  <td>{s.open_season_start} &ndash; {s.open_season_end}</td>
                  <td>{s.season_max_nights}</td>
                  <td>{FIXED_PROCESSING_FEE_LABEL}</td>
                  <td>${s.guest_fee_per_day}/day</td>
                  <td className="actions-cell">
                    {renderSeasonActions(s)}
                  </td>
                </tr>
              ))}
              {seasons.length === 0 && (
                <tr>
                  <td colSpan={10} style={{ textAlign: "center", opacity: 0.6 }}>
                    No booking seasons configured
                  </td>
                </tr>
              )}
            </tbody>
          </table>
      </div>
      <div className="admin-mobile-only">
        {seasons.length === 0 ? (
          <div className="admin-mobile-empty">No booking seasons configured</div>
        ) : (
          <div className="admin-mobile-compact-list">
            {seasons.map((season) => (
              <AdminMobileRow
                key={season.id}
                eyebrow="Booking Season"
                badge={<span className="badge badge-onseason">{season.season_max_nights} nights</span>}
                title={season.year}
                meta={[
                  `Prime: ${season.prime_season_start} - ${season.prime_season_end}`,
                  `Open: ${season.open_season_start} - ${season.open_season_end}`,
                  `Fee ${FIXED_PROCESSING_FEE_LABEL} • Guest $${season.guest_fee_per_day}/day`,
                  season.rounds.map((round) =>
                    `R${round.round_number} ${round.start_date}-${round.end_date}`
                  ).join(" • "),
                ]}
                actions={renderSeasonActions(season)}
              />
            ))}
          </div>
        )}
      </div>
      {(editingSeason || showCreateModal) && (
        <SeasonModal
          season={editingSeason}
          onClose={() => {
            setEditingSeason(null);
            setShowCreateModal(false);
          }}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
