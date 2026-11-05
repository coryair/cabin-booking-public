import { useState } from "react";


interface NotificationPreferencesModalProps {
  enabled: boolean;
  onClose: () => void;
  onSave: (enabled: boolean) => Promise<void>;
}


export function NotificationPreferencesModal({
  enabled,
  onClose,
  onSave,
}: NotificationPreferencesModalProps) {
  const [checked, setChecked] = useState(enabled);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave(checked);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save notification preferences");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal notification-preferences-modal" onClick={(event) => event.stopPropagation()}>
        <h2>Notification Preferences</h2>
        <p className="notification-preferences-intro">
          Choose whether Cabin Booking should email you when a cancellation opens bookable cabin dates.
        </p>
        <label className="notification-preference-option">
          <input
            type="checkbox"
            checked={checked}
            onChange={(event) => setChecked(event.target.checked)}
            disabled={saving}
          />
          <span>
            <strong>Cancellation availability alerts</strong>
            <small>Email me when a paid reservation cancellation makes dates available.</small>
          </span>
        </label>
        <p className="field-hint">
          This setting affects only cancellation availability emails. Reservation confirmations and other account emails are unchanged.
        </p>
        {error && <div className="modal-error">{error}</div>}
        <div className="modal-actions">
          <button type="button" className="cancel-btn" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="button" className="confirm-btn" onClick={() => void handleSave()} disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
