import { useState, useEffect } from "react";
import type { BookingSeason } from "../../types";
import { adminApi } from "../../api/admin";

interface TimeTravelAdminProps {
  onChanged: () => void;
}

export function TimeTravelAdmin({ onChanged }: TimeTravelAdminProps) {
  const [date, setDate] = useState("");
  const [isActive, setIsActive] = useState(false);
  const [simulatedDate, setSimulatedDate] = useState<string | null>(null);
  const [season, setSeason] = useState<BookingSeason | null>(null);
  const [saving, setSaving] = useState(false);

  const fetchStatus = async () => {
    try {
      const data = await adminApi.timeTravelStatus();
      setIsActive(data.active);
      setSimulatedDate(data.simulated_date);
    } catch {
      // The controls remain usable when status cannot be loaded.
    }
  };

  const fetchSeason = async () => {
    try {
      setSeason(await adminApi.currentSeason());
    } catch {
      // Quick-jump buttons are omitted when season data is unavailable.
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchSeason();
  }, []);

  const jumpTo = async (targetDate: string) => {
    setSaving(true);
    try {
      const data = await adminApi.setTimeTravel(targetDate);
      setIsActive(data.active);
      setSimulatedDate(data.simulated_date);
      onChanged();
    } catch {
      // Preserve the previous simulated date when the update fails.
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setSaving(true);
    try {
      const data = await adminApi.resetTimeTravel();
      setIsActive(data.active);
      setSimulatedDate(data.simulated_date);
      onChanged();
    } catch {
      // Preserve the current simulated date when reset fails.
    } finally {
      setSaving(false);
    }
  };

  const handleSetDate = () => {
    if (date) jumpTo(date);
  };

  const formatLabel = (d: string) =>
    new Date(d + "T00:00:00").toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });

  return (
    <div className="time-travel-controls">
      <div className="time-travel-status">
        {isActive && simulatedDate ? (
          <span className="time-travel-active-label">
            Simulating: {formatLabel(simulatedDate)}
          </span>
        ) : (
          <span className="time-travel-inactive-label">Time Travel</span>
        )}
      </div>

      <div className="time-travel-actions">
        {season && (
          <div className="time-travel-quick-jumps">
            {season.rounds.map((r) => (
              <button
                key={r.round_number}
                className="time-travel-quick-btn"
                onClick={() => jumpTo(r.start_date)}
                disabled={saving}
                title={`Jump to ${r.start_date}`}
              >
                R{r.round_number}
              </button>
            ))}
            <button
              className="time-travel-quick-btn"
              onClick={() => jumpTo(season.open_season_start)}
              disabled={saving}
              title={`Jump to ${season.open_season_start}`}
            >
              Open
            </button>
          </div>
        )}

        <div className="time-travel-custom">
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="time-travel-date-input"
          />
          <button
            className="time-travel-go-btn"
            onClick={handleSetDate}
            disabled={!date || saving}
          >
            Go
          </button>
        </div>

        {isActive && (
          <button
            className="time-travel-reset-btn"
            onClick={reset}
            disabled={saving}
          >
            Reset
          </button>
        )}
      </div>
    </div>
  );
}
