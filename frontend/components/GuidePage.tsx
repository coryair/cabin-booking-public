import { useEffect, useState } from "react";
import type { BookingSeason, Document, Shareholder } from "../types";
import { adminApi } from "../api/admin";

export function GuidePage() {
  const [season, setSeason] = useState<BookingSeason | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [shares, setShares] = useState<{ share_id: string; share_name: string; priority: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedRound, setExpandedRound] = useState<number | null>(null);

  useEffect(() => {
    document.documentElement.classList.add("scrollable-page");
    return () => document.documentElement.classList.remove("scrollable-page");
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      adminApi.currentSeason(controller.signal).catch(() => null),
      adminApi.shareholders(controller.signal).catch(() => []),
      adminApi.documents(controller.signal).catch(() => []),
    ]).then(([seasonData, shareholders, docs]) => {
      if (controller.signal.aborted) return;
      setSeason(seasonData);
      setDocuments(docs);
      const all: Shareholder[] = shareholders;
      // Deduplicate shares by share_id, sorted by priority
      const seen = new Set<string>();
      const uniqueShares: { share_id: string; share_name: string; priority: number }[] = [];
      for (const s of all) {
        if (!seen.has(s.share) && s.priority > 0) {
          seen.add(s.share);
          uniqueShares.push({ share_id: s.share, share_name: s.share_name || s.share, priority: s.priority });
        }
      }
      uniqueShares.sort((a, b) => a.priority - b.priority);
      setShares(uniqueShares);
      setLoading(false);
    });
    return () => controller.abort();
  }, []);

  const fmtDate = (iso: string) => {
    const d = new Date(iso + "T12:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  const getShareWindows = (rnd: BookingSeason["rounds"][0]) => {
    const sorted = rnd.priority_order === "priority"
      ? [...shares]
      : [...shares].reverse();
    const roundStart = new Date(rnd.start_date + "T12:00:00");
    return sorted.map((share, i) => {
      const start = new Date(roundStart);
      start.setDate(start.getDate() + i * rnd.window_days);
      const end = new Date(start);
      end.setDate(end.getDate() + rnd.window_days - 1);
      return { ...share, windowStart: start, windowEnd: end };
    });
  };

  const fmtWindow = (d: Date) =>
    d.toLocaleDateString("en-US", { month: "short", day: "numeric" });

  return (
    <div className="guide-page">
      <div className="guide-header">
        <h1>Booking Guide</h1>
      </div>

      {loading ? (
        <div className="guide-loading"><div className="spinner" /></div>
      ) : (
        <div className="guide-content">
          {/* How to Book */}
          <section className="guide-section">
            <h2>How to Book</h2>
            <ol className="guide-steps">
              <li>Tap a start date on the calendar, then tap an end date to select your range</li>
              <li>Choose your cabin(s) and number of guests</li>
              <li>Review the cost breakdown and confirm</li>
            </ol>
            <p className="guide-note"><br />You'll receive a confirmation email after each completed reservation. During priority rounds, you'll get a reminder email the day before your booking window opens.</p>
          </section>

          {/* Round Schedule */}
          {season && season.rounds.length > 0 && (
            <section className="guide-section">
              <h2>{season.year} Round Schedule</h2>
              <div className="guide-rounds">
                <div className="guide-round-card guide-round-prime">
                  <div className="guide-round-header">
                    <span className="guide-round-label">Prime Season</span>
                    <span className="guide-round-dates">
                      {fmtDate(season.prime_season_start)} – {fmtDate(season.prime_season_end)}
                    </span>
                  </div>
                  <div className="guide-round-details">
                    <span>Rounds 1-3 apply</span>
                    <span className="guide-detail-sep">&middot;</span>
                    <span>{season.season_max_nights}-night season cap</span>
                  </div>
                </div>
                {season.rounds.map((rnd) => {
                  const isExpanded = expandedRound === rnd.round_number;
                  const windows = isExpanded ? getShareWindows(rnd) : [];
                  return (
                    <div key={rnd.id} className={`guide-round-card ${isExpanded ? "expanded" : ""}`}>
                      <button
                        className="guide-round-toggle"
                        onClick={() => setExpandedRound(isExpanded ? null : rnd.round_number)}
                      >
                        <div className="guide-round-header">
                          <span className="guide-round-label">
                            Round {rnd.round_number}
                            <span className="guide-round-hint">
                              {isExpanded ? "– tap to collapse" : "– tap for details"}
                            </span>
                          </span>
                          <span className="guide-round-dates">
                            {fmtDate(rnd.start_date)} – {fmtDate(rnd.end_date)}
                          </span>
                          <svg className={`guide-round-chevron ${isExpanded ? "open" : ""}`} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="6 9 12 15 18 9" />
                          </svg>
                        </div>
                        <div className="guide-round-details">
                          <span>{rnd.window_days}-day booking windows</span>
                          <span className="guide-detail-sep">&middot;</span>
                          <span>Max {rnd.max_reservations} reservation{rnd.max_reservations !== 1 ? "s" : ""}</span>
                          {rnd.max_nights && (
                            <>
                              <span className="guide-detail-sep">&middot;</span>
                              <span>Max {rnd.max_nights} nights</span>
                            </>
                          )}
                          <span className="guide-detail-sep">&middot;</span>
                          <span>{rnd.priority_order === "priority" ? "Priority order" : "Reverse order"}</span>
                          <span className="guide-detail-sep">&middot;</span>
                          <span>{season.season_max_nights}-night season cap</span>
                        </div>
                      </button>
                      {isExpanded && windows.length > 0 && (
                        <div className="guide-round-schedule">
                          <div className="guide-schedule-header">
                            <span>Share</span>
                            <span>Booking Window</span>
                          </div>
                          {windows.map((w) => (
                            <div key={w.share_id} className="guide-schedule-row">
                              <span className="guide-schedule-share">{w.share_name}</span>
                              <span className="guide-schedule-dates">{fmtWindow(w.windowStart)} – {fmtWindow(w.windowEnd)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
                <div className="guide-round-card guide-round-open">
                  <div className="guide-round-header">
                    <span className="guide-round-label">Open Season</span>
                    <span className="guide-round-dates">
                      {fmtDate(season.open_season_start)} – {fmtDate(season.open_season_end)}
                    </span>
                  </div>
                  <div className="guide-round-details">
                    <span>First come, first served</span>
                    <span className="guide-detail-sep">&middot;</span>
                    <span>30-day advance booking limit</span>
                    <span className="guide-detail-sep">&middot;</span>
                    <span>No night cap</span>
                  </div>
                </div>
              </div>
            </section>
          )}

          {/* Documents & Links */}
          {documents.length > 0 && (
            <section className="guide-section">
              <h2>Documents</h2>
              <div className="guide-documents">
                {documents.map((doc) => (
                  <a key={doc.id} href={doc.url} target="_blank" rel="noopener noreferrer" className="guide-doc-link">
                    <svg className="guide-doc-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                      <polyline points="14 2 14 8 20 8"></polyline>
                      <line x1="16" y1="13" x2="8" y2="13"></line>
                      <line x1="16" y1="17" x2="8" y2="17"></line>
                    </svg>
                    <div>
                      <span className="guide-doc-title">{doc.title}</span>
                      {doc.description && <span className="guide-doc-desc">{doc.description}</span>}
                    </div>
                    <svg className="guide-doc-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                      <polyline points="15 3 21 3 21 9"></polyline>
                      <line x1="10" y1="14" x2="21" y2="3"></line>
                    </svg>
                  </a>
                ))}
              </div>
            </section>
          )}

        </div>
      )}
    </div>
  );
}
