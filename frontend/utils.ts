import type { BookingStatus, Cabin, Reservation } from "./types";

/**
 * Get the current CSS zoom factor applied to the document root.
 * Needed because getBoundingClientRect returns viewport pixels,
 * but position:fixed interprets values in zoomed coordinates.
 */
export function getZoom(): number {
  return parseFloat(getComputedStyle(document.documentElement).zoom || "1") || 1;
}

/**
 * Map a round key to a human-readable label.
 */
export function roundLabel(round: string): string {
  switch (round) {
    case "round_1": return "Round 1";
    case "round_2": return "Round 2 (Reverse Priority)";
    case "round_3": return "Round 3";
    case "open": return "Open Season";
    case "offseason": return "Off-Season";
    case "between_rounds": return "Between Rounds";
    default: return round;
  }
}

/**
 * Get the display name for a cabin by its ID.
 */
export function getCabinName(cabins: Cabin[], cabinId: string): string {
  const cabin = cabins.find((c) => c.cabin_id === cabinId);
  return cabin?.cabin_name || cabinId;
}

/**
 * Get initials from a share/family name (e.g. "The Smiths" -> "S", "Van Horn" -> "VH").
 */
export function getInitials(name: string): string {
  if (!name) return "";
  const words = name.replace(/^the\s+/i, "").trim().split(/\s+/);
  return words.map((w) => w[0]?.toUpperCase() || "").join("").slice(0, 2);
}

/**
 * Format a YYYY-MM-DD date string for display.
 * Uses noon to avoid timezone-related off-by-one issues.
 */
/**
 * Describe the next booking phase and how far away it is.
 */
export function nextPhaseText(status: BookingStatus, effectiveToday?: string): string | null {
  if (!status.next_phase || !status.next_phase_date) return null;
  const today = effectiveToday ? new Date(effectiveToday + "T00:00:00") : new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(status.next_phase_date + "T00:00:00");
  const days = Math.round((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
  const dateLabel = formatDate(status.next_phase_date);
  const verb = status.next_phase!.toLowerCase().includes("ends") ? "" : " starts";
  if (days > 0 && days <= 90) {
    return `${status.next_phase}${verb} ${dateLabel} (${days} day${days === 1 ? "" : "s"})`;
  }
  if (days > 0) {
    return `${status.next_phase}${verb} ${dateLabel}`;
  }
  return null;
}

export function formatDate(
  dateStr: string,
  options: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" }
): string {
  const d = new Date(dateStr + "T12:00:00");
  return d.toLocaleDateString("en-US", options);
}

export function nightCount(r: Reservation): number {
  const s = new Date(r.start_date + "T00:00:00");
  const e = new Date(r.end_date + "T00:00:00");
  return Math.max(1, Math.round((e.getTime() - s.getTime()) / 86_400_000));
}

export function isActive(r: Reservation): boolean {
  return r.status !== "cancelled" && r.status !== "refunded";
}
