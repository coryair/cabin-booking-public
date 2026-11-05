import { useState, useEffect } from "react";
import { CabinSelector } from "./CabinSelector";
import { InfoTip } from "./Tooltip";
import { GuestNightsEditor } from "./GuestNightsEditor";
import { useAppData } from "../context/AppDataContext";
import { getCabinName, formatDate, roundLabel } from "../utils";
import type { CabinType, Cabin, BookingStatus, BookingEligibility, CostPreview } from "../types";
import { calendarApi } from "../api/calendar";
import { reservationsApi } from "../api/reservations";

interface BookingModalProps {
  startDate: string;
  endDate: string;
  cabins: Cabin[];
  bookingStatus: BookingStatus | null;
  onClose: () => void;
  onSuccess: () => void;
  checkAvailability: (start: string, end: string, signal?: AbortSignal) => Promise<Record<string, boolean>>;
}

export function BookingModal({
  startDate,
  endDate,
  cabins,
  bookingStatus,
  onClose,
  onSuccess,
  checkAvailability,
}: BookingModalProps) {
  const [selectedCabins, setSelectedCabins] = useState<CabinType[]>([]);
  const [isDayUse, setIsDayUse] = useState<boolean | null>(null);
  const [guestNights, setGuestNights] = useState<number[]>([]);
  const [availability, setAvailability] = useState<Record<string, boolean>>({});
  const [costPreview, setCostPreview] = useState<CostPreview | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [submitResult, setSubmitResult] = useState<"success" | "failed" | null>(null);
  const [eligibility, setEligibility] = useState<BookingEligibility | null>(null);
  const [eligibilityLoading, setEligibilityLoading] = useState(true);
  const { shareholder, activeShareId, activeShare } = useAppData();

  const handleNext = () => {
    if (step === 1 && selectedCabins.length === 0) {
      setError("Please select a cabin");
      return;
    }
    if (step === 1 && stepOneBlockReason) {
      setError(null);
      return;
    }
    if (step === 2 && isDayUse === null) {
      setError("Please select overnight or day use");
      return;
    }
    setError(null);
    setStep((s) => Math.min(s + 1, 3) as 1 | 2 | 3);
  };

  const handleBack = () => {
    setError(null);
    setStep((s) => Math.max(s - 1, 1) as 1 | 2 | 3);
  };

  useEffect(() => {
    const controller = new AbortController();
    const fetchData = async () => {
      setIsLoading(true);
      try {
        const avail = await checkAvailability(startDate, endDate, controller.signal);
        if (controller.signal.aborted) return;
        setAvailability(avail);

        // Auto-select and auto-advance if only one cabin is available
        const availableCabinIds = Object.entries(avail)
          .filter(([_, isAvailable]) => isAvailable)
          .map(([id]) => id as CabinType);
        if (availableCabinIds.length === 1) {
          setSelectedCabins(availableCabinIds);
        }
      } catch {
        if (!controller.signal.aborted) setError("Failed to check availability");
      } finally {
        if (!controller.signal.aborted) setIsLoading(false);
      }
    };

    void fetchData();
    return () => controller.abort();
  }, [startDate, endDate, checkAvailability]);

  useEffect(() => {
    const shareId = activeShareId || shareholder?.share;
    if (!shareId) {
      setEligibility(null);
      setEligibilityLoading(false);
      return;
    }

    const controller = new AbortController();

    const fetchEligibility = async () => {
      setEligibilityLoading(true);
      try {
        const data = await calendarApi.eligibility(startDate, endDate, shareId, controller.signal);
        setEligibility(data);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setEligibility({
          eligible: false,
          reason: err instanceof Error ? err.message : "Failed to check booking eligibility",
          booking_round: null,
          current_round: null,
        });
      } finally {
        if (!controller.signal.aborted) setEligibilityLoading(false);
      }
    };

    fetchEligibility();

    return () => controller.abort();
  }, [startDate, endDate, activeShareId, shareholder]);

  // Fetch cost preview when cabins change
  useEffect(() => {
    if (selectedCabins.length === 0) {
      setCostPreview(null);
      return;
    }

    const controller = new AbortController();

    const fetchCost = async () => {
      try {
        const data = await calendarApi.cost({
          startDate,
          endDate,
          cabins: selectedCabins,
          isDayUse: Boolean(isDayUse),
          guestNights,
        }, controller.signal);
        setCostPreview(data);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        // Cost preview is non-critical, keep going
      }
    };

    fetchCost();

    return () => controller.abort();
  }, [selectedCabins, startDate, endDate, isDayUse, guestNights]);

  const formatBookingDate = (dateStr: string) =>
    formatDate(dateStr, { weekday: "short", month: "short", day: "numeric" });

  const activeBookingStatus = bookingStatus;

  const formatWindow = () => {
    if (!activeBookingStatus?.window_start || !activeBookingStatus?.window_end) return null;
    return `${formatDate(activeBookingStatus.window_start)} \u2013 ${formatDate(activeBookingStatus.window_end)}`;
  };

  const handleSubmit = async () => {
    if (selectedCabins.length === 0) {
      setError("Please select a cabin");
      return;
    }
    if (stepOneBlockReason) {
      setError(stepOneBlockReason);
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const { checkout_url, reservation_id } = await reservationsApi.checkout({
        share: activeShareId || shareholder?.share || "",
        cabins: selectedCabins,
        start_date: startDate,
        end_date: endDate,
        guest_count: guestNights.length,
        guest_nights: guestNights,
        is_day_use: isDayUse,
      });
      if (!checkout_url || !reservation_id) {
        throw new Error("Payment setup did not return a valid checkout session");
      }
      window.location.href = checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create booking");
      setSubmitResult("failed");
      setIsSubmitting(false);
    }
  };

  const isSingleDay = startDate === endDate;

  // Multi-day defaults to overnight; same-day is inferred as day-use.
  useEffect(() => {
    if (isSingleDay) {
      // Same-day selections are interpreted as day-use.
      setIsDayUse(true);
      return;
    }
    setIsDayUse(false);
  }, [isSingleDay]);

  const noneAvailable = cabins.length > 0 && Object.values(availability).every((v) => !v);
  const inRound = ["round_1", "round_2", "round_3"].includes(activeBookingStatus?.current_round ?? "");
  const roundDisplay = activeBookingStatus ? roundLabel(activeBookingStatus.current_round) : "";
  const windowStr = formatWindow();

  const requestedNights = Math.max(1, Math.round(
    (new Date(endDate + "T00:00:00").getTime() - new Date(startDate + "T00:00:00").getTime()) / 86400000
  ));
  const stepOneBlockReason = eligibility?.eligible === false ? eligibility.reason : null;

  const maxGuestUnits = requestedNights;

  useEffect(() => {
    if (!stepOneBlockReason || noneAvailable || step === 1) return;
    setStep(1);
    setError(null);
  }, [stepOneBlockReason, noneAvailable, step]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal booking-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header-bar" />
        <h2>CABIN RESERVATION</h2>

        {/* Round context info */}
        {activeBookingStatus && (
          <div className="booking-round-info">
            <div className="round-label">{roundDisplay}</div>
            {activeShare && (
              <div className="guide-round-details">
                Booking as: {activeShare.share_name}
              </div>
            )}
            <div className="guide-round-details">
              {(() => {
                const parts: string[] = [];
                if (activeBookingStatus.priority != null && activeBookingStatus.total_shares != null) parts.push(`Priority ${activeBookingStatus.priority} of ${activeBookingStatus.total_shares}`);
                if (windowStr) parts.push(`Your Booking Window: ${windowStr}`);
                return parts.map((text, i) => (
                  <span key={i}>
                    {i > 0 && <span className="guide-detail-sep"> &middot; </span>}
                    {text}
                  </span>
                ));
              })()}
            </div>
            <div className="guide-round-details">
              {(() => {
                const parts: string[] = [];
                if (activeBookingStatus.round_max_nights != null) parts.push(`${activeBookingStatus.round_max_nights - activeBookingStatus.round_nights} round nights remaining`);
                if (activeBookingStatus.season_max_nights > 0 && inRound) parts.push(`${activeBookingStatus.season_max_nights - activeBookingStatus.nights_used} season nights left`);
                return parts.length > 0 ? parts.map((text, i) => (
                  <span key={i}>
                    {i > 0 && <span className="guide-detail-sep"> &middot; </span>}
                    {text}
                  </span>
                )) : null;
              })()}
            </div>
          </div>
        )}

        <div className="date-display">
          <div className="date-detail">
            <span className="date-label">{isDayUse ? "Date" : "Check-in"}</span>
            <span>{formatBookingDate(startDate)}</span>
          </div>
          {!isDayUse && (
            <>
              <span className="date-arrow">&rarr;</span>
              <div className="date-detail">
                <span className="date-label">Checkout</span>
                <span>{formatBookingDate(endDate)}</span>
              </div>
            </>
          )}
          <span className="date-nights">({requestedNights} {isDayUse ? "day" : "night(s)"})</span>
        </div>

        {submitResult ? (
          <>
            <div className={`wizard-result ${submitResult}`}>
              {submitResult === "success" ? (
                <>
                  <svg className="wizard-result-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <path d="M8 12l3 3 5-5" />
                  </svg>
                  <h3 className="wizard-result-title">Booking Confirmed</h3>
                  <p className="wizard-result-detail">
                    {selectedCabins.map((c) => getCabinName(cabins, c)).join(" & ")}
                  </p>
                </>
              ) : (
                <>
                  <svg className="wizard-result-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <path d="M15 9l-6 6M9 9l6 6" />
                  </svg>
                  <h3 className="wizard-result-title">Booking Failed</h3>
                  {error && <p className="wizard-result-error">{error}</p>}
                </>
              )}
            </div>
            <div className="wizard-actions">
              {submitResult === "failed" && (
                <button
                  onClick={onClose}
                  className="back-btn"
                >
                  Try Again
                </button>
              )}
              <button
                onClick={() => { if (submitResult === "success") onSuccess(); else onClose(); }}
                className="confirm-btn"
                style={submitResult === "failed" ? undefined : { marginLeft: "auto" }}
              >
                Done
              </button>
            </div>
          </>
        ) : isLoading || eligibilityLoading ? (
          <div className="modal-loading">
            <div className="spinner" />
            <p>Checking availability...</p>
          </div>
        ) : noneAvailable ? (
          <div className="no-availability">
            <p>Sorry, all cabins are booked for these dates.</p>
            <p>Please select different dates.</p>
          </div>
        ) : (
          <>
            <div className="wizard-steps">
              <div className={`wizard-step ${step >= 1 ? "active" : ""} ${step === 1 ? "current" : ""} ${step > 1 ? "completed" : ""}`}>
                <span className="wizard-step-number">1</span>
                <span className="wizard-step-label">Cabin</span>
              </div>
              <div className="wizard-step-line" />
              <div className={`wizard-step ${step >= 2 ? "active" : ""} ${step === 2 ? "current" : ""} ${step > 2 ? "completed" : ""}`}>
                <span className="wizard-step-number">2</span>
                <span className="wizard-step-label">Type</span>
              </div>
              <div className="wizard-step-line" />
              <div className={`wizard-step ${step >= 3 ? "active" : ""} ${step === 3 ? "current" : ""} ${step > 3 ? "completed" : ""}`}>
                <span className="wizard-step-number">3</span>
                <span className="wizard-step-label">Details</span>
              </div>
              <div className="wizard-step-line" />
              <div className={`wizard-step ${step >= 3 ? "active" : ""}`}>
                <span className="wizard-step-number">4</span>
                <span className="wizard-step-label">Pay</span>
              </div>
            </div>

            <div className="wizard-content">
              {step === 1 && (
                <div className="wizard-panel" key="step-1">
                  <div className="form-group">
                    <label>Select Cabin <InfoTip text="Select a cabin for your stay" /></label>
                    <CabinSelector
                      selectedCabins={selectedCabins}
                      onChange={setSelectedCabins}
                      availability={availability}
                      cabins={cabins}
                    />
                  </div>
                  {stepOneBlockReason && (
                    <div className="booking-blocked-msg">
                      {stepOneBlockReason}
                    </div>
                  )}
                </div>
              )}

              {step === 2 && (
                <div className="wizard-panel" key="step-2">
                  <div className="form-group">
                    <label>Reservation Type</label>
                    <div className="reservation-type-toggle">
                      <button
                        type="button"
                        className={`toggle-btn ${isDayUse === false ? "active" : ""}`}
                        onClick={() => setIsDayUse(false)}
                        disabled={isSingleDay}
                      >
                        Overnight
                      </button>
                      <button
                        type="button"
                        className={`toggle-btn ${isDayUse === true ? "active" : ""}`}
                        onClick={() => setIsDayUse(true)}
                        disabled={!isSingleDay}
                      >
                        Day Use
                      </button>
                    </div>
                    {isSingleDay ? (
                      <p className="field-hint">Selecting the same day twice is automatically treated as day use</p>
                    ) : (
                      <p className="field-hint">Day use requires a single-day selection</p>
                    )}
                  </div>
                </div>
              )}

              {step === 3 && (
                <div className="wizard-panel" key="step-3">
                  <GuestNightsEditor
                    guestNights={guestNights}
                    onChange={setGuestNights}
                    maxUnits={maxGuestUnits}
                    sectionLabel="Guests"
                    helperText="Only pay for the nights each guest actually stays."
                    emptyText="No non-family guests added."
                  />

                  {costPreview && selectedCabins.length > 0 && (
                    <div className="cost-display">
                      <div className="cost-row">
                        <span>{costPreview.nights} {isDayUse ? "day" : "night"}{costPreview.nights !== 1 ? "s" : ""}</span>
                        <span>${isDayUse ? costPreview.daily_rate : costPreview.nightly_rate}/{isDayUse ? "day" : "night"} <InfoTip text={`Rate is per ${isDayUse ? "day" : "night"}, per cabin`} /></span>
                      </div>
                      <div className="cost-row">
                        <span>Subtotal</span>
                        <span>${costPreview.base_cost.toFixed(2)}</span>
                      </div>
                      {costPreview.guest_fee > 0 && (
                        <div className="cost-row">
                          <span>
                            Guest fee ({costPreview.guest_nights_total} guest-{isDayUse ? "days" : "nights"} × ${costPreview.guest_fee_rate}/{isDayUse ? "day" : "night"})
                          </span>
                          <span>${costPreview.guest_fee.toFixed(2)}</span>
                        </div>
                      )}
                      <div className="cost-row">
                        <span>Processing fee ({(costPreview.fee_pct * 100).toFixed(0)}%)</span>
                        <span>${costPreview.processing_fee.toFixed(2)}</span>
                      </div>
                      <div className="cost-row total">
                        <span>Total</span>
                        <span>${costPreview.total.toFixed(2)}</span>
                      </div>
                    </div>
                  )}
                </div>
              )}

            </div>

            {error && <p className="modal-error">{error}</p>}

            <div className="wizard-actions">
              <button onClick={onClose} className="cancel-btn" disabled={isSubmitting}>
                Cancel
              </button>
              <div className="wizard-nav-buttons">
                {step > 1 && (
                  <button onClick={handleBack} className="back-btn" disabled={isSubmitting}>
                    Back
                  </button>
                )}
                {step < 3 ? (
                  <button
                    onClick={handleNext}
                    className="confirm-btn"
                    disabled={step === 1 && (selectedCabins.length === 0 || Boolean(stepOneBlockReason))}
                  >
                    {step === 1 && stepOneBlockReason ? "Booking Unavailable" : "Next"}
                  </button>
                ) : (
                  <button
                    onClick={handleSubmit}
                    className="confirm-btn"
                    disabled={isSubmitting || selectedCabins.length === 0 || Boolean(stepOneBlockReason)}
                  >
                    {isSubmitting ? "Processing..." : stepOneBlockReason ? "Booking Unavailable" : process.env.BUN_PUBLIC_DEMO_MODE === "true" ? "Confirm Demo Booking" : "Confirm & Pay"}
                  </button>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
