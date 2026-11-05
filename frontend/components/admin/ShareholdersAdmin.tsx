import React, { useState, useEffect, useCallback } from "react";
import { InfoTip } from "../Tooltip";
import { AdminMobileRow } from "./AdminMobileRow";
import type { Shareholder, ShareholderRole, ShareholderUpdate } from "../../types";
import { adminApi } from "../../api/admin";
import {
  invitationsApi,
  type AvailableInvitationShare as AvailableShare,
  type Invitation,
} from "../../api/invitations";

function getShareholderRole(shareholder: Pick<Shareholder, "is_viewer" | "is_analytics" | "is_admin" | "is_superadmin">): ShareholderRole {
  if (shareholder.is_superadmin) return "superadmin";
  if (shareholder.is_admin) return "admin";
  if (shareholder.is_analytics) return "analytics";
  if (shareholder.is_viewer) return "viewer";
  return "user";
}

function getRoleBadge(role: ShareholderRole) {
  if (role === "superadmin") return <span className="badge badge-superadmin">Superadmin</span>;
  if (role === "admin") return <span className="badge badge-admin">Admin</span>;
  if (role === "analytics") return <span className="badge badge-admin">Analytics</span>;
  if (role === "viewer") return <span className="badge badge-user">Viewer</span>;
  return <span className="badge badge-user">User</span>;
}

interface EditModalProps {
  shareholder: Shareholder;
  availableShares: AvailableShare[];
  onClose: () => void;
  onSave: (id: number, update: ShareholderUpdate) => Promise<void>;
}

function EditModal({ shareholder, availableShares, onClose, onSave }: EditModalProps) {
  const initialAdditionalShares = (shareholder.allowed_shares || [])
    .map((s) => s.share_id)
    .filter((shareId) => shareId !== shareholder.share);
  const [formData, setFormData] = useState({
    first_name: shareholder.first_name,
    last_name: shareholder.last_name,
    email: shareholder.email,
    phone_number: shareholder.phone_number || "",
    role: getShareholderRole(shareholder),
    password: "",
    additional_shares: initialAdditionalShares,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      const update: ShareholderUpdate = {};
      if (formData.first_name !== shareholder.first_name) update.first_name = formData.first_name;
      if (formData.last_name !== shareholder.last_name) update.last_name = formData.last_name;
      if (formData.email !== shareholder.email) update.email = formData.email;
      if (formData.phone_number !== (shareholder.phone_number || "")) update.phone_number = formData.phone_number || null;
      const originalRole = getShareholderRole(shareholder);
      if (formData.role !== originalRole) {
        update.is_viewer = formData.role === "viewer";
        update.is_analytics = formData.role === "analytics";
        update.is_admin = formData.role === "admin";
        update.is_superadmin = formData.role === "superadmin";
      }
      if (formData.password) update.password = formData.password;
      const existingAdditional = [...initialAdditionalShares].sort();
      const updatedAdditional = [...formData.additional_shares].sort();
      if (JSON.stringify(existingAdditional) !== JSON.stringify(updatedAdditional)) {
        update.additional_shares = updatedAdditional;
      }

      await onSave(shareholder.id, update);
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
        <h3>Edit Shareholder</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-group">
              <label>First Name</label>
              <input
                type="text"
                className="form-input"
                value={formData.first_name}
                onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Last Name</label>
              <input
                type="text"
                className="form-input"
                value={formData.last_name}
                onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                required
              />
            </div>
          </div>
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              className="form-input"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              required
            />
          </div>
          <div className="form-group">
            <label>Phone</label>
            <input
              type="tel"
              className="form-input"
              value={formData.phone_number}
              onChange={(e) => setFormData({ ...formData, phone_number: e.target.value })}
              placeholder="(555) 555-5555"
            />
          </div>
          <div className="form-group">
            <label>New Password (leave blank to keep current)</label>
            <input
              type="password"
              className="form-input"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              placeholder="Enter new password"
            />
          </div>
          <div className="form-group">
            <label>Role</label>
            <select
              className="form-input"
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value as ShareholderRole })}
            >
              <option value="viewer">Viewer</option>
              <option value="user">User</option>
              <option value="analytics">Analytics</option>
              <option value="admin">Admin</option>
              <option value="superadmin">Superadmin</option>
            </select>
            <p className="field-hint">
              {formData.role === "viewer"
                ? "Viewer can only see the assigned share calendar."
                : formData.role === "analytics"
                  ? "Analytics can view Overview and Analytics in the admin panel."
                : formData.role === "admin"
                  ? "Admin can manage reservations and cabins."
                  : formData.role === "superadmin"
                    ? "Superadmin can also manage shareholders and rates."
                    : "User can book for the assigned share."}
            </p>
          </div>
          <div className="form-group">
            <label>Additional Share Access</label>
            <div className="admin-checkbox-list">
              {availableShares
                .filter((s) => s.share_id !== shareholder.share)
                .map((s) => (
                  <label key={s.share_id} className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={formData.additional_shares.includes(s.share_id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setFormData((prev) => ({
                            ...prev,
                            additional_shares: [...prev.additional_shares, s.share_id],
                          }));
                          return;
                        }
                        setFormData((prev) => ({
                          ...prev,
                          additional_shares: prev.additional_shares.filter((id) => id !== s.share_id),
                        }));
                      }}
                    />
                    {s.share_name}
                  </label>
                ))}
            </div>
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

interface InviteModalProps {
  availableShares: AvailableShare[];
  onClose: () => void;
  onInvited: () => void;
}

function InviteModal({ availableShares, onClose, onInvited }: InviteModalProps) {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [email, setEmail] = useState("");
  const [selectedShare, setSelectedShare] = useState(availableShares[0]?.share_id || "");
  const [role, setRole] = useState<ShareholderRole>("user");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!firstName.trim() || !lastName.trim() || !email.trim() || !selectedShare) return;

    setSending(true);
    setError(null);

    try {
      await invitationsApi.create({
        email: email.trim(),
        share: selectedShare,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone_number: phoneNumber.trim() || null,
        is_viewer: role === "viewer",
      });
      onInvited();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send invitation");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal admin-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Send Invitation</h3>
        {availableShares.length === 0 ? (
          <>
            <p className="invite-no-shares">All shares have been assigned. No invitations can be sent.</p>
            <div className="modal-actions">
              <button type="button" className="cancel-btn" onClick={onClose}>
                Close
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>Share</label>
              <select
                className="form-input"
                value={selectedShare}
                onChange={(e) => setSelectedShare(e.target.value)}
                disabled={sending}
              >
                {availableShares.map((s) => (
                  <option key={s.share_id} value={s.share_id}>
                    {s.share_name}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Role</label>
              <select
                className="form-input"
                value={role}
                onChange={(e) => setRole(e.target.value as ShareholderRole)}
                disabled={sending}
              >
                <option value="user">User</option>
                <option value="viewer">Viewer</option>
              </select>
              <p className="field-hint">
                {role === "viewer"
                  ? "Viewer can only see the assigned share calendar."
                  : "User can book for the assigned share."}
              </p>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>First Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  disabled={sending}
                  required
                />
              </div>
              <div className="form-group">
                <label>Last Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  disabled={sending}
                  required
                />
              </div>
            </div>
            <div className="form-group">
              <label>Phone</label>
              <input
                type="tel"
                className="form-input"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                placeholder="(555) 555-5555"
                disabled={sending}
              />
            </div>
            <div className="form-group">
              <label>Email</label>
              <input
                type="email"
                className="form-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email address"
                disabled={sending}
                required
              />
            </div>
            {error && <div className="modal-error">{error}</div>}
            <div className="modal-actions">
              <button type="button" className="cancel-btn" onClick={onClose}>
                Cancel
              </button>
              <button type="submit" className="confirm-btn" disabled={sending || !firstName.trim() || !lastName.trim() || !email.trim()}>
                {sending ? "Sending..." : "Send Invite"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

const formatDate = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

const isExpired = (expiresAt: string) => {
  return new Date(expiresAt) < new Date();
};

export function ShareholdersAdmin() {
  const [shareholders, setShareholders] = useState<Shareholder[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingShareholder, setEditingShareholder] = useState<Shareholder | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [availableShares, setAvailableShares] = useState<AvailableShare[]>([]);
  const [showInviteModal, setShowInviteModal] = useState(false);

  const fetchShareholders = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await adminApi.shareholders(signal);
      if (!signal?.aborted) setShareholders(data);
    } catch (err) {
      if (!signal?.aborted) console.error("Failed to fetch shareholders:", err);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  const fetchInvitations = useCallback(async (signal?: AbortSignal) => {
    try {
      const [invites, shares] = await Promise.all([
        invitationsApi.list(signal),
        invitationsApi.availableShares(signal),
      ]);
      if (!signal?.aborted) {
        setInvitations(invites);
        setAvailableShares(shares);
      }
    } catch {
      if (!signal?.aborted) console.error("Failed to fetch invitations");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void fetchShareholders(controller.signal);
    void fetchInvitations(controller.signal);
    return () => controller.abort();
  }, [fetchInvitations, fetchShareholders]);

  const handleSave = async (shareholderId: number, update: ShareholderUpdate) => {
    await adminApi.updateShareholder(shareholderId, update);
    await fetchShareholders();
  };

  const handleDelete = async (shareholderId: number) => {
    if (!confirm("Are you sure you want to delete this shareholder?")) return;

    setDeleting(shareholderId);
    setError(null);
    try {
      await adminApi.deleteShareholder(shareholderId);
      await fetchShareholders();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete shareholder");
    } finally {
      setDeleting(null);
    }
  };

  const handleRevoke = async (id: string) => {
    setError(null);
    try {
      await invitationsApi.revoke(id);
      await fetchInvitations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke invitation");
    }
  };

  const renderShareholderActions = (sh: Shareholder) => (
    <>
      <button className="action-btn edit-btn" onClick={() => setEditingShareholder(sh)}>
        Edit
      </button>
      <button
        className="action-btn delete-btn"
        onClick={() => handleDelete(sh.id)}
        disabled={deleting === sh.id}
      >
        {deleting === sh.id ? "..." : "Delete"}
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
        <h2>Shareholders</h2>
        <button className="add-btn" onClick={() => setShowInviteModal(true)}>
          + Invite
        </button>
      </div>
      {error && <div className="modal-error">{error}</div>}
      <div className="admin-desktop-only admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Share</th>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Priority <InfoTip text="Lower number = higher booking priority" /></th>
                <th>Role</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {shareholders.map((sh) => (
                <tr key={sh.id}>
                  <td>{sh.share_name || sh.share}</td>
                  <td>{sh.first_name} {sh.last_name}</td>
                  <td>{sh.email}</td>
                  <td>{sh.phone_number || "-"}</td>
                  <td>{sh.priority}</td>
                  <td>{getRoleBadge(getShareholderRole(sh))}</td>
                  <td className="actions-cell">
                    {renderShareholderActions(sh)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
      </div>
      <div className="admin-mobile-only">
        <div className="admin-mobile-compact-list">
          {shareholders.map((sh) => (
            <AdminMobileRow
              key={sh.id}
              eyebrow={sh.share_name || sh.share}
              badge={getRoleBadge(getShareholderRole(sh))}
              title={`${sh.first_name} ${sh.last_name}`}
              meta={[sh.email, sh.phone_number || "No phone", `Priority ${sh.priority}`]}
              actions={renderShareholderActions(sh)}
            />
          ))}
        </div>
      </div>

      {invitations.length > 0 && (
        <>
          <h3 className="invite-pending-header">Pending Invitations</h3>
          <div className="admin-desktop-only admin-table-container">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Share</th>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Sent</th>
                    <th>Expires</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {invitations.map((inv) => (
                    <tr key={inv.id} className={isExpired(inv.expires_at) ? "invite-expired-row" : ""}>
                      <td>{inv.share_name || inv.share}</td>
                      <td>{inv.first_name} {inv.last_name}</td>
                      <td>{inv.email}</td>
                      <td>{getRoleBadge(inv.is_viewer ? "viewer" : "user")}</td>
                      <td>{inv.created_at ? formatDate(inv.created_at) : "-"}</td>
                      <td>
                        {formatDate(inv.expires_at)}
                        {isExpired(inv.expires_at) && <span className="badge badge-expired">Expired</span>}
                      </td>
                      <td className="actions-cell">
                        <button
                          className="action-btn delete-btn"
                          onClick={() => handleRevoke(inv.id)}
                        >
                          Revoke
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
          </div>
          <div className="admin-mobile-only">
            <div className="admin-mobile-compact-list">
              {invitations.map((inv) => (
                <AdminMobileRow
                  key={inv.id}
                  muted={isExpired(inv.expires_at)}
                  eyebrow={inv.share_name || inv.share}
                  badge={getRoleBadge(inv.is_viewer ? "viewer" : "user")}
                  title={`${inv.first_name} ${inv.last_name}`}
                  meta={[
                    inv.email,
                    inv.created_at ? `Sent ${formatDate(inv.created_at)}` : "Sent -",
                    `Expires ${formatDate(inv.expires_at)}${isExpired(inv.expires_at) ? " • Expired" : ""}`,
                  ]}
                  actions={
                    <button className="action-btn delete-btn" onClick={() => handleRevoke(inv.id)}>
                      Revoke
                    </button>
                  }
                />
              ))}
            </div>
          </div>
        </>
      )}

      {editingShareholder && (
        <EditModal
          shareholder={editingShareholder}
          availableShares={availableShares}
          onClose={() => setEditingShareholder(null)}
          onSave={handleSave}
        />
      )}
      {showInviteModal && (
        <InviteModal
          availableShares={availableShares}
          onClose={() => setShowInviteModal(false)}
          onInvited={() => fetchInvitations()}
        />
      )}
    </div>
  );
}
