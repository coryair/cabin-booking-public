export type CabinType = "pine" | "cedar";

export type ReservationStatus = "reserved" | "unpaid" | "paid" | "cancelled" | "refunded";
export type ShareholderRole = "viewer" | "user" | "analytics" | "admin" | "superadmin";

export interface AllowedShare {
  share_id: string;
  share_name: string;
  priority: number;
}

export interface Shareholder {
  id: number;
  share: string;
  share_name?: string;
  priority: number;
  first_name: string;
  last_name: string;
  email: string;
  phone_number?: string | null;
  last_booked: string | null;
  is_viewer: boolean;
  is_analytics: boolean;
  is_admin: boolean;
  is_superadmin: boolean;
  tour_seen: boolean;
  cancellation_availability_emails_enabled: boolean;
  allowed_shares: AllowedShare[];
  can_access_multiple_shares: boolean;
  created_at: string | null;
}

export interface Reservation {
  id: number;
  share: string;
  share_name?: string;
  booked_by_shareholder_id?: number | null;
  booked_by_shareholder_name?: string | null;
  cabins: CabinType[];
  start_date: string; // YYYY-MM-DD
  end_date: string; // YYYY-MM-DD
  guest_count: number;
  guest_nights?: number[];
  cost: number;
  booking_round?: string | null;
  base_cost?: number | null;
  processing_fee?: number | null;
  is_day_use?: boolean;
  guest_fee?: number | null;
  status: ReservationStatus;
  stripe_checkout_session_id?: string | null;
  stripe_payment_intent_id?: string | null;
  created_at: string | null;
  cancelled_at?: string | null;
  refund_amount?: number | null;
  refunded_at?: string | null;
  stripe_refund_id?: string | null;
  cancellation_reason?: string | null;
}

export interface CreateReservationInput {
  share?: string;
  cabins: CabinType[];
  start_date: string;
  end_date: string;
  guest_count: number;
  guest_nights?: number[];
  is_day_use: boolean;
}

export interface CalendarDayReservation {
  id: number;
  share: string;
  share_name?: string;
  booked_by_short_name?: string;
  calendar_display_name?: string;
  cabins: CabinType[];
  guest_count: number;
  is_day_use: boolean;
  status: Extract<ReservationStatus, "paid" | "unpaid">;
  is_checkout: boolean;
}

export type ReservationSegmentType = "single" | "start" | "middle" | "end";

export interface ReservationSegmentMeta {
  segment: ReservationSegmentType;
  showLabel: boolean;
}

export interface CalendarDay {
  date: string; // YYYY-MM-DD
  day: number;
  reservations: CalendarDayReservation[];
}

export interface MonthData {
  year: number;
  month: number;
  days: CalendarDay[];
}

export interface AvailabilityResponse {
  available: boolean;
  cabins: Record<string, boolean>;
  conflicts: Reservation[];
}

export interface Cabin {
  id: number;
  cabin_id: string;
  cabin_name: string;
  description: string | null;
  max_guests: number;
  created_at: string | null;
}

export interface Rate {
  id: number;
  season: "offseason" | "onseason";
  nightly_rate: number;
  daily_rate: number;
  effective_date: string;
}

export interface ShareholderUpdate {
  share?: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  phone_number?: string | null;
  password?: string;
  is_viewer?: boolean;
  is_analytics?: boolean;
  is_admin?: boolean;
  is_superadmin?: boolean;
  additional_shares?: string[];
  cancellation_availability_emails_enabled?: boolean;
}

export interface CabinUpdate {
  cabin_name?: string;
  description?: string;
  max_guests?: number;
}

export interface RateUpdate {
  season?: "offseason" | "onseason";
  nightly_rate?: number;
  daily_rate?: number;
  effective_date?: string;
}

export interface ReservationSelfUpdate {
  guest_count?: number;
  guest_nights?: number[];
}

export interface ReservationAdminUpdate {
  guest_count?: number;
  guest_nights?: number[];
  start_date?: string;
  end_date?: string;
  cabins?: CabinType[];
  status?: ReservationStatus;
}

export interface Document {
  id: number;
  title: string;
  url: string;
  description: string | null;
  sort_order: number;
  created_at: string | null;
}

export interface BookingStatus {
  current_round: string;
  current_round_display: string;
  can_book: boolean;
  reason: string | null;
  window_start: string | null;
  window_end: string | null;
  nights_used: number;
  nights_remaining: number;
  season_max_nights: number;
  round_reservations: number;
  round_max_reservations: number;
  round_nights: number;
  round_max_nights: number | null;
  now_booking_share_name: string | null;
  priority: number | null;
  total_shares: number | null;
  next_phase: string | null;
  next_phase_date: string | null;
  prime_season_start: string | null;
  prime_season_end: string | null;
}

export interface BookingEligibility {
  eligible: boolean;
  reason: string | null;
  booking_round: string | null;
  current_round: string | null;
}

export interface CostPreview {
  base_cost: number;
  processing_fee: number;
  total: number;
  nightly_rate: number;
  daily_rate: number;
  nights: number;
  cabin_count: number;
  season_type: string;
  fee_pct: number;
  is_day_use: boolean;
  guest_fee: number;
  guest_fee_rate: number;
  guest_count: number;
  guest_nights_total: number;
}

export interface GuestAdjustmentPreview {
  reservation_id: number;
  allowed: boolean;
  reason: string | null;
  action: "collect" | "refund" | "apply" | "none";
  edit_deadline: string | null;
  current_guest_nights: number[];
  updated_guest_nights: number[];
  current_guest_count: number;
  updated_guest_count: number;
  current_guest_nights_total: number;
  updated_guest_nights_total: number;
  current_guest_fee: number;
  updated_guest_fee: number;
  current_processing_fee: number;
  updated_processing_fee: number;
  current_total: number;
  updated_total: number;
  delta_guest_fee: number;
  delta_processing_fee: number;
  delta_total: number;
  charge_amount: number;
  refund_amount: number;
  requested_refund_amount: number;
  processing_fee_retained: number;
  processing_fee_retained_total: number;
  policy_fee_target: number;
  reservation_status: ReservationStatus;
}

export interface GuestAdjustmentCheckoutResult {
  reservation_id: number;
  adjustment_id: number;
  checkout_url: string;
}

export interface GuestAdjustmentApplyResult {
  reservation: Reservation;
  action: "apply" | "refund" | "none";
  adjustment_id?: number | null;
  refund_issued: boolean;
  refund_amount?: number | null;
  message: string;
}

export interface GuestAdjustmentReconcileResult {
  status: "paid" | "pending" | "applied" | "failed" | "cancelled" | "refunded";
  adjustment_id: number;
  reservation_id: number;
}

export interface BookingRound {
  id: number;
  season_id: number;
  round_number: number;
  start_date: string;
  end_date: string;
  window_days: number;
  max_reservations: number;
  max_nights: number | null;
  priority_order: string;
}

export interface BookingSeason {
  id: number;
  year: number;
  prime_season_start: string;
  prime_season_end: string;
  open_season_start: string;
  open_season_end: string;
  season_max_nights: number;
  processing_fee_pct: number;
  guest_fee_per_day: number;
  rounds: BookingRound[];
}

export interface RefundPreview {
  eligible: boolean;
  cancellation_eligible: boolean;
  days_until_checkin: number;
  refund_amount: number;
  requested_refund_amount: number;
  processing_fee_kept: number;
  policy_fee_target: number;
  status: string;
  reason: string;
  admin_override?: boolean;
  override_required?: boolean;
}

export interface CancelResult {
  status: string;
  refund_issued: boolean;
  refund_amount: number | null;
  message: string;
}
