interface GuestNightsEditorProps {
  guestNights: number[];
  onChange: (next: number[]) => void;
  maxUnits: number;
  disabled?: boolean;
  sectionLabel?: string;
  helperText?: string;
  emptyText?: string;
}

export function GuestNightsEditor({
  guestNights,
  onChange,
  maxUnits,
  disabled = false,
  sectionLabel = "Current Guests",
  helperText = "Only pay for the nights each guest actually stays.",
  emptyText = "No non-family guests added.",
}: GuestNightsEditorProps) {
  const clamp = (value: number) => Math.min(Math.max(1, value), Math.max(1, maxUnits));

  const updateRow = (index: number, value: number) => {
    const next = [...guestNights];
    next[index] = clamp(value);
    onChange(next);
  };

  const addGuest = () => {
    onChange([...guestNights, 1]);
  };

  const removeGuest = (index: number) => {
    onChange(guestNights.filter((_, i) => i !== index));
  };

  return (
    <div className="form-group guest-nights-editor">
      <div className="label-row">
        <label>{sectionLabel}</label>
      </div>
      {helperText && <p className="field-hint">{helperText}</p>}

      {guestNights.length === 0 ? (
        <p className="field-hint">{emptyText}</p>
      ) : (
        <div className="guest-nights-rows" role="table" aria-label="Guest nights">
          <div className="guest-nights-header" role="row">
            <div className="guest-nights-header-cell">Guest</div>
            <div className="guest-nights-header-cell">Guest Nights</div>
            <div className="guest-nights-header-cell guest-nights-actions-header">Actions</div>
          </div>
          {guestNights.map((nights, index) => (
            <div key={`guest-${index}`} className="guest-nights-row" role="row">
              <div className="guest-nights-row-label">Guest {index + 1}</div>
              <div className="guest-nights-row-input">
                <label className="guest-nights-inline-label" htmlFor={`guest-nights-${index}`}>Guest Nights</label>
                <div className="stepper">
                  <button
                    type="button"
                    className="stepper-btn"
                    onClick={() => updateRow(index, nights - 1)}
                    disabled={disabled || nights <= 1}
                    aria-label={`Decrease Guest ${index + 1} nights`}
                  >
                    -
                  </button>
                  <input
                    id={`guest-nights-${index}`}
                    type="number"
                    className="stepper-input"
                    min={1}
                    max={maxUnits}
                    value={nights}
                    disabled={disabled}
                    onChange={(e) => updateRow(index, parseInt(e.target.value, 10) || 1)}
                  />
                  <button
                    type="button"
                    className="stepper-btn"
                    onClick={() => updateRow(index, nights + 1)}
                    disabled={disabled || nights >= maxUnits}
                    aria-label={`Increase Guest ${index + 1} nights`}
                  >
                    +
                  </button>
                </div>
              </div>
              <button
                type="button"
                className="cancel-btn guest-nights-remove-btn"
                onClick={() => removeGuest(index)}
                disabled={disabled}
                aria-label={`Remove Guest ${index + 1}`}
              >
                <span className="guest-nights-remove-label">Remove</span>
                <span className="guest-nights-remove-icon" aria-hidden="true">&times;</span>
              </button>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 10 }}>
        <button
          type="button"
          className="back-btn"
          onClick={addGuest}
          disabled={disabled}
          aria-label="Add a guest"
          style={{ padding: "6px 10px" }}
        >
          + Add a guest
        </button>
      </div>
    </div>
  );
}
