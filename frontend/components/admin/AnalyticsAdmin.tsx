import { useState, useMemo } from "react";
import type { Reservation, BookingSeason, CabinType } from "../../types";
import { nightCount, isActive } from "../../utils";
import { useAdminData } from "../../hooks/useAdminData";

function isPriorityRound(r: Reservation): boolean {
  return r.booking_round != null && r.booking_round !== "open_season";
}

function cabinNights(r: Reservation, cabin: CabinType): number {
  if (!r.cabins.includes(cabin)) return 0;
  return nightCount(r);
}

function daysBetween(start: string, end: string): number {
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  return Math.max(0, Math.round((e.getTime() - s.getTime()) / 86_400_000));
}

function monthRange(
  year: number,
  month: number,
  seasonStart: string,
  seasonEnd: string
): { start: string; end: string; nights: number } | null {
  const mStart = new Date(year, month, 1);
  const mEnd = new Date(year, month + 1, 1);
  const sStart = new Date(seasonStart + "T00:00:00");
  const sEnd = new Date(seasonEnd + "T00:00:00");

  const effStart = mStart > sStart ? mStart : sStart;
  const effEnd = mEnd < sEnd ? mEnd : sEnd;

  if (effStart >= effEnd) return null;

  const startStr = effStart.toISOString().slice(0, 10);
  const endStr = effEnd.toISOString().slice(0, 10);
  return { start: startStr, end: endStr, nights: daysBetween(startStr, endStr) };
}

function bookedNightsInRange(
  reservations: Reservation[],
  rangeStart: string,
  rangeEnd: string,
  cabin?: CabinType
): number {
  let total = 0;
  for (const r of reservations) {
    if (cabin && !r.cabins.includes(cabin)) continue;
    const rStart = r.start_date > rangeStart ? r.start_date : rangeStart;
    const rEnd = r.end_date < rangeEnd ? r.end_date : rangeEnd;
    if (rStart < rEnd) {
      total += daysBetween(rStart, rEnd);
    }
  }
  return total;
}

function pct(available: number, booked: number): number {
  return available > 0 ? Math.round(((available - booked) / available) * 100) : 0;
}

/** Count Friday + Saturday nights in a date range */
function countWeekendNights(start: string, end: string): number {
  let count = 0;
  const cur = new Date(start + "T00:00:00");
  const endDate = new Date(end + "T00:00:00");
  while (cur < endDate) {
    const day = cur.getDay();
    if (day === 5 || day === 6) count++; // Friday or Saturday
    cur.setDate(cur.getDate() + 1);
  }
  return count;
}

/** Count booked weekend nights for reservations in a range, optionally filtered by cabin */
function bookedWeekendNightsInRange(
  reservations: Reservation[],
  rangeStart: string,
  rangeEnd: string,
  cabin?: CabinType
): number {
  let total = 0;
  for (const r of reservations) {
    if (cabin && !r.cabins.includes(cabin)) continue;
    const rStart = r.start_date > rangeStart ? r.start_date : rangeStart;
    const rEnd = r.end_date < rangeEnd ? r.end_date : rangeEnd;
    if (rStart < rEnd) {
      total += countWeekendNights(rStart, rEnd);
    }
  }
  return total;
}

/** Filter active reservations that overlap a season's date range */
function reservationsForSeason(reservations: Reservation[], season: BookingSeason): Reservation[] {
  return reservations.filter(
    (r) => r.start_date < season.open_season_end && r.end_date > season.open_season_start
  );
}

interface MonthAvailability {
  label: string;
  start: string;
  end: string;
  totalNights: number;
  pineBooked: number;
  cedarBooked: number;
  availability: number;
  pineAvailability: number;
  cedarAvailability: number;
}

interface ShareholderStats {
  name: string;
  priority: number;
  priorityStays: number;
  totalNights: number;
  pineNights: number;
  cedarNights: number;
  months: {
    label: string;
    nights: number;
    pineNights: number;
    cedarNights: number;
  }[];
}

const CABINS: { key: CabinType; label: string }[] = [
  { key: "pine", label: "Pine" },
  { key: "cedar", label: "Cedar" },
];

export function AnalyticsAdmin() {
  const { reservations, season, seasons, shareholders, loading, error } = useAdminData();
  const [selectedYear, setSelectedYear] = useState<number | null>(null);

  const sortedSeasons = useMemo(
    () => [...seasons].sort((a, b) => b.year - a.year),
    [seasons]
  );

  const selectedSeason = useMemo(() => {
    if (selectedYear != null) return sortedSeasons.find((s) => s.year === selectedYear) || null;
    return season;
  }, [selectedYear, sortedSeasons, season]);

  const activeForSeason = useMemo(() => {
    const allActive = reservations.filter(isActive);
    if (!selectedSeason) return allActive;
    return reservationsForSeason(allActive, selectedSeason);
  }, [reservations, selectedSeason]);

  const months = useMemo(() => {
    if (!selectedSeason) return [];
    const result: MonthAvailability[] = [];
    const end = new Date(selectedSeason.prime_season_end + "T00:00:00");

    let cur = new Date(new Date(selectedSeason.prime_season_start + "T00:00:00").getFullYear(), new Date(selectedSeason.prime_season_start + "T00:00:00").getMonth(), 1);
    while (cur < end) {
      const range = monthRange(cur.getFullYear(), cur.getMonth(), selectedSeason.prime_season_start, selectedSeason.prime_season_end);
      if (range && range.nights > 0) {
        const pineBooked = bookedNightsInRange(activeForSeason, range.start, range.end, "pine");
        const cedarBooked = bookedNightsInRange(activeForSeason, range.start, range.end, "cedar");
        const totalCabinNights = range.nights * 2;
        const totalBooked = pineBooked + cedarBooked;

        result.push({
          label: cur.toLocaleDateString("en-US", { month: "long" }),
          start: range.start,
          end: range.end,
          totalNights: range.nights,
          pineBooked,
          cedarBooked,
          availability: pct(totalCabinNights, totalBooked),
          pineAvailability: pct(range.nights, pineBooked),
          cedarAvailability: pct(range.nights, cedarBooked),
        });
      }
      cur = new Date(cur.getFullYear(), cur.getMonth() + 1, 1);
    }
    return result;
  }, [activeForSeason, selectedSeason]);

  const overall = useMemo(() => {
    if (!selectedSeason) return { availability: 0, pineAvailability: 0, cedarAvailability: 0, totalNights: 0, pineBooked: 0, cedarBooked: 0 };
    const totalNights = daysBetween(selectedSeason.prime_season_start, selectedSeason.prime_season_end);
    const pineBooked = bookedNightsInRange(activeForSeason, selectedSeason.prime_season_start, selectedSeason.prime_season_end, "pine");
    const cedarBooked = bookedNightsInRange(activeForSeason, selectedSeason.prime_season_start, selectedSeason.prime_season_end, "cedar");
    return {
      availability: pct(totalNights * 2, pineBooked + cedarBooked),
      pineAvailability: pct(totalNights, pineBooked),
      cedarAvailability: pct(totalNights, cedarBooked),
      totalNights,
      pineBooked,
      cedarBooked,
    };
  }, [activeForSeason, selectedSeason]);

  const weekendStats = useMemo(() => {
    if (!selectedSeason) return null;
    const totalWeekendNights = countWeekendNights(selectedSeason.prime_season_start, selectedSeason.prime_season_end);
    const pineBooked = bookedWeekendNightsInRange(activeForSeason, selectedSeason.prime_season_start, selectedSeason.prime_season_end, "pine");
    const cedarBooked = bookedWeekendNightsInRange(activeForSeason, selectedSeason.prime_season_start, selectedSeason.prime_season_end, "cedar");
    const totalBooked = pineBooked + cedarBooked;
    const totalAvailable = totalWeekendNights * 2;

    const byMonth = months.map((m) => {
      const mWeekends = countWeekendNights(m.start, m.end);
      const mPine = bookedWeekendNightsInRange(activeForSeason, m.start, m.end, "pine");
      const mCedar = bookedWeekendNightsInRange(activeForSeason, m.start, m.end, "cedar");
      return {
        label: m.label,
        total: mWeekends,
        pineBooked: mPine,
        cedarBooked: mCedar,
        booked: mPine + mCedar,
        bookedPct: pct(mWeekends * 2, mPine + mCedar),
      };
    });

    return {
      totalWeekendNights,
      totalAvailable,
      totalBooked,
      pineBooked,
      cedarBooked,
      bookedPct: pct(totalAvailable, totalBooked),
      pinePct: pct(totalWeekendNights, pineBooked),
      cedarPct: pct(totalWeekendNights, cedarBooked),
      byMonth,
    };
  }, [activeForSeason, selectedSeason, months]);

  const shareholderStats = useMemo((): ShareholderStats[] => {
    if (!selectedSeason) return [];

    const shareMap = new Map<string, { name: string; priority: number }>();
    for (const sh of shareholders) {
      shareMap.set(sh.share, { name: sh.share_name || `${sh.first_name} ${sh.last_name}`, priority: sh.priority });
    }

    const byShare = new Map<string, Reservation[]>();
    for (const r of activeForSeason) {
      const list = byShare.get(r.share) || [];
      list.push(r);
      byShare.set(r.share, list);
    }

    const stats: ShareholderStats[] = [];
    const allShares = new Set([...shareMap.keys(), ...byShare.keys()]);

    for (const share of allShares) {
      const info = shareMap.get(share) || { name: share, priority: 99 };
      const resos = byShare.get(share) || [];

      const priorityStays = resos.filter((r) => {
        if (!isPriorityRound(r) || !selectedSeason) return false;
        // Only count if the reservation has nights within prime season
        const rStart = r.start_date > selectedSeason.prime_season_start ? r.start_date : selectedSeason.prime_season_start;
        const rEnd = r.end_date < selectedSeason.prime_season_end ? r.end_date : selectedSeason.prime_season_end;
        return rEnd > rStart;
      }).length;
      let totalNights = 0;
      let pineNights = 0;
      let cedarNights = 0;

      const monthStats = months.map((m) => {
        const hN = bookedNightsInRange(resos, m.start, m.end, "pine");
        const wN = bookedNightsInRange(resos, m.start, m.end, "cedar");
        return { label: m.label, nights: hN + wN, pineNights: hN, cedarNights: wN };
      });

      if (selectedSeason) {
        totalNights = bookedNightsInRange(resos, selectedSeason.prime_season_start, selectedSeason.prime_season_end);
        pineNights = bookedNightsInRange(resos, selectedSeason.prime_season_start, selectedSeason.prime_season_end, "pine");
        cedarNights = bookedNightsInRange(resos, selectedSeason.prime_season_start, selectedSeason.prime_season_end, "cedar");
      } else {
        for (const r of resos) {
          totalNights += nightCount(r);
          pineNights += cabinNights(r, "pine");
          cedarNights += cabinNights(r, "cedar");
        }
      }

      stats.push({
        name: `${info.name} - ${info.priority}`,
        priority: info.priority,
        priorityStays,
        totalNights,
        pineNights,
        cedarNights,
        months: monthStats,
      });
    }

    stats.sort((a, b) => a.priority - b.priority);
    return stats;
  }, [activeForSeason, selectedSeason, shareholders, months]);

  const seasonTotals = useMemo(() => {
    const paidRevenue = activeForSeason
      .filter((r) => r.status === "paid")
      .reduce((sum, r) => sum + r.cost, 0);
    const pendingRevenue = activeForSeason
      .filter((r) => r.status !== "paid")
      .reduce((sum, r) => sum + r.cost, 0);
    const totalNights = selectedSeason
      ? bookedNightsInRange(activeForSeason, selectedSeason.prime_season_start, selectedSeason.prime_season_end)
      : activeForSeason.reduce((sum, r) => sum + nightCount(r), 0);
    return { paidRevenue, pendingRevenue, totalNights, totalReservations: activeForSeason.length };
  }, [activeForSeason, selectedSeason]);

  const totalsRow = useMemo(() => {
    const totalNights = shareholderStats.reduce((s, sh) => s + sh.totalNights, 0);
    const pineNights = shareholderStats.reduce((s, sh) => s + sh.pineNights, 0);
    const cedarNights = shareholderStats.reduce((s, sh) => s + sh.cedarNights, 0);
    const monthTotals = months.map((m, i) => ({
      label: m.label,
      nights: shareholderStats.reduce((s, sh) => s + (sh.months[i]?.nights || 0), 0),
      pineNights: shareholderStats.reduce((s, sh) => s + (sh.months[i]?.pineNights || 0), 0),
      cedarNights: shareholderStats.reduce((s, sh) => s + (sh.months[i]?.cedarNights || 0), 0),
    }));
    return { totalNights, pineNights, cedarNights, months: monthTotals };
  }, [shareholderStats, months]);

  if (loading) {
    return (
      <div className="admin-loading">
        <div className="spinner" />
      </div>
    );
  }

  if (error) {
    return <div className="admin-section admin-error">{error}</div>;
  }

  const year = selectedSeason?.year || new Date().getFullYear();
  const cabinAvailability = (cabin: CabinType) =>
    cabin === "pine" ? "pineAvailability" : "cedarAvailability" as const;

  return (
    <div className="admin-section analytics-section">
      <div className="admin-section-header">
        <h2>Analytics - {year} High Season</h2>
        {sortedSeasons.length > 1 && (
          <div className="analytics-year-selector">
            {sortedSeasons.map((s) => (
              <button
                key={s.year}
                type="button"
                className={`analytics-year-btn${s.year === year ? " active" : ""}`}
                onClick={() => setSelectedYear(s.year)}
              >
                {s.year}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="analytics-cards">
        <div className="analytics-card analytics-card-primary">
          <span className="analytics-card-label">Total Availability</span>
          <span className="analytics-card-value">{overall.availability}%</span>
          <span className="analytics-card-detail">
            {overall.totalNights * 2 - overall.pineBooked - overall.cedarBooked} of {overall.totalNights * 2} cabin-nights open
          </span>
        </div>
        {months.map((m) => (
          <div key={m.label} className="analytics-card">
            <span className="analytics-card-label">{m.label}</span>
            <span className="analytics-card-value">{m.availability}%</span>
            <span className="analytics-card-detail">
              {m.totalNights * 2 - m.pineBooked - m.cedarBooked} of {m.totalNights * 2} open
            </span>
          </div>
        ))}
      </div>

      <div className="overview-totals">
        <div className="overview-total-item">
          <span className="overview-total-value">{seasonTotals.totalReservations}</span>
          <span className="overview-total-label">Reservations</span>
        </div>
        <div className="overview-total-item">
          <span className="overview-total-value">{seasonTotals.totalNights}</span>
          <span className="overview-total-label">Nights Booked</span>
        </div>
        <div className="overview-total-item">
          <span className="overview-total-value overview-total-paid">
            ${seasonTotals.paidRevenue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
          </span>
          <span className="overview-total-label">Collected</span>
        </div>
        {seasonTotals.pendingRevenue > 0 && (
          <div className="overview-total-item">
            <span className="overview-total-value overview-total-pending">
              ${seasonTotals.pendingRevenue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            </span>
            <span className="overview-total-label">Pending</span>
          </div>
        )}
      </div>

      <div className="analytics-cabin-grid">
        {CABINS.map(({ key, label }) => (
          <div key={key} className="analytics-cabin-section">
            <h3 className={`analytics-cabin-title ${key}`}>{label}</h3>
            <div className="analytics-cards">
              <div className="analytics-card analytics-card-primary">
                <span className="analytics-card-label">{label} Availability</span>
                <span className="analytics-card-value">{overall[cabinAvailability(key)]}%</span>
                <span className="analytics-card-detail">
                  {overall.totalNights - (key === "pine" ? overall.pineBooked : overall.cedarBooked)} of {overall.totalNights} nights open
                </span>
              </div>
              {months.map((m) => (
                <div key={m.label} className="analytics-card">
                  <span className="analytics-card-label">{m.label}</span>
                  <span className="analytics-card-value">{m[cabinAvailability(key)]}%</span>
                  <span className="analytics-card-detail">
                    {m.totalNights - (key === "pine" ? m.pineBooked : m.cedarBooked)} of {m.totalNights} open
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {weekendStats && (
        <div className="overview-panel analytics-weekend-panel">
          <h3 className="overview-panel-label">Weekend Availability</h3>
          <div className="analytics-cards">
            <div className="analytics-card analytics-card-primary">
              <span className="analytics-card-label">Weekend Availability</span>
              <span className="analytics-card-value">{weekendStats.bookedPct}%</span>
              <span className="analytics-card-detail">
                {weekendStats.totalAvailable - weekendStats.totalBooked} of {weekendStats.totalAvailable} nights open
              </span>
            </div>
            {CABINS.map(({ key, label }) => {
              const booked = key === "pine" ? weekendStats.pineBooked : weekendStats.cedarBooked;
              const avail = key === "pine" ? weekendStats.pinePct : weekendStats.cedarPct;
              return (
                <div key={key} className="analytics-card">
                  <span className="analytics-card-label">{label}</span>
                  <span className="analytics-card-value">{avail}%</span>
                  <span className="analytics-card-detail">
                    {weekendStats.totalWeekendNights - booked} of {weekendStats.totalWeekendNights} nights open
                  </span>
                </div>
              );
            })}
            {weekendStats.byMonth.map((m) => (
              <div key={m.label} className="analytics-card">
                <span className="analytics-card-label">{m.label}</span>
                <span className="analytics-card-value">{m.bookedPct}%</span>
                <span className="analytics-card-detail">
                  {m.total * 2 - m.booked} of {m.total * 2} nights open
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="overview-panel analytics-table-panel">
        <h3 className="overview-panel-label">Shareholder Breakdown</h3>
        <div className="admin-table-container">
          <table className="admin-table analytics-table">
            <thead>
              <tr>
                <th>Shareholder</th>
                <th className="analytics-num">Priority Stays</th>
                <th className="analytics-num">Total Nights</th>
                <th className="analytics-num">Pine Nights</th>
                <th className="analytics-num">Cedar Nights</th>
                {months.map((m) => (
                  <th key={m.label} className="analytics-num">{m.label} Nights</th>
                ))}
                {months.map((m) => (
                  <th key={`h-${m.label}`} className="analytics-num analytics-sub-col">{m.label} Pine</th>
                ))}
                {months.map((m) => (
                  <th key={`w-${m.label}`} className="analytics-num analytics-sub-col">{m.label} Cedar</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shareholderStats.map((sh) => (
                <tr key={sh.name}>
                  <td className="analytics-shareholder-name">{sh.name}</td>
                  <td className="analytics-num">{sh.priorityStays}</td>
                  <td className="analytics-num">{sh.totalNights}</td>
                  <td className="analytics-num">{sh.pineNights}</td>
                  <td className="analytics-num">{sh.cedarNights}</td>
                  {sh.months.map((m) => (
                    <td key={m.label} className="analytics-num">{m.nights}</td>
                  ))}
                  {sh.months.map((m) => (
                    <td key={`h-${m.label}`} className="analytics-num analytics-sub-col">{m.pineNights}</td>
                  ))}
                  {sh.months.map((m) => (
                    <td key={`w-${m.label}`} className="analytics-num analytics-sub-col">{m.cedarNights}</td>
                  ))}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="analytics-totals-row">
                <td className="analytics-shareholder-name">TOTAL</td>
                <td className="analytics-num"></td>
                <td className="analytics-num">{totalsRow.totalNights}</td>
                <td className="analytics-num">{totalsRow.pineNights}</td>
                <td className="analytics-num">{totalsRow.cedarNights}</td>
                {totalsRow.months.map((m) => (
                  <td key={m.label} className="analytics-num">{m.nights}</td>
                ))}
                {totalsRow.months.map((m) => (
                  <td key={`h-${m.label}`} className="analytics-num analytics-sub-col">{m.pineNights}</td>
                ))}
                {totalsRow.months.map((m) => (
                  <td key={`w-${m.label}`} className="analytics-num analytics-sub-col">{m.cedarNights}</td>
                ))}
              </tr>
              <tr className="analytics-available-row">
                <td className="analytics-shareholder-name" colSpan={2}>Total Available Reservation Nights</td>
                <td className="analytics-num">{overall.totalNights * 2}</td>
                <td className="analytics-num">{overall.totalNights}</td>
                <td className="analytics-num">{overall.totalNights}</td>
                {months.map((m) => (
                  <td key={m.label} className="analytics-num">{m.totalNights * 2}</td>
                ))}
                {months.map((m) => (
                  <td key={`h-${m.label}`} className="analytics-num analytics-sub-col">{m.totalNights}</td>
                ))}
                {months.map((m) => (
                  <td key={`w-${m.label}`} className="analytics-num analytics-sub-col">{m.totalNights}</td>
                ))}
              </tr>
              <tr className="analytics-pct-row">
                <td className="analytics-shareholder-name" colSpan={2}>% Availability</td>
                <td className="analytics-num">{overall.availability}%</td>
                <td className="analytics-num">{overall.pineAvailability}%</td>
                <td className="analytics-num">{overall.cedarAvailability}%</td>
                {months.map((m) => (
                  <td key={m.label} className="analytics-num">{m.availability}%</td>
                ))}
                {months.map((m) => (
                  <td key={`h-${m.label}`} className="analytics-num analytics-sub-col">{m.pineAvailability}%</td>
                ))}
                {months.map((m) => (
                  <td key={`w-${m.label}`} className="analytics-num analytics-sub-col">{m.cedarAvailability}%</td>
                ))}
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </div>
  );
}
