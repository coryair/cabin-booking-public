import { useEffect, useState } from "react";

import { authApi } from "../api/auth";
import { AppLink } from "./AppLink";


interface CancellationAvailabilityUnsubscribeProps {
  token: string;
}


type ValidationState = {
  valid: boolean;
  subscribed: boolean;
  email: string | null;
};


export function CancellationAvailabilityUnsubscribe({ token }: CancellationAvailabilityUnsubscribeProps) {
  const [validation, setValidation] = useState<ValidationState | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [unsubscribed, setUnsubscribed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setError(null);
    void authApi.validateCancellationAvailabilityUnsubscribe(token, controller.signal)
      .then((result) => {
        if (active) setValidation(result);
      })
      .catch((err: unknown) => {
        if (!active || (err instanceof DOMException && err.name === "AbortError")) return;
        if (active) setError("This unsubscribe link could not be verified.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [token]);

  const confirmUnsubscribe = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await authApi.unsubscribeCancellationAvailability(token);
      setUnsubscribed(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update this preference");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card unsubscribe-card">
        <div className="login-badge">
          <div className="badge-border">
            <h1>Cabin Booking</h1>
          </div>
        </div>
        {loading && <div className="spinner" />}
        {!loading && (error || !validation?.valid) && (
          <>
            <h2>Link unavailable</h2>
            <p className="login-error">{error || "This unsubscribe link is invalid."}</p>
          </>
        )}
        {!loading && validation?.valid && !unsubscribed && (
          <>
            <h2>Turn off cancellation alerts?</h2>
            <p>
              Stop cancellation availability emails for <strong>{validation.email}</strong>. Other Cabin Booking account and reservation emails will continue.
            </p>
            {!validation.subscribed ? (
              <p className="modal-success">These alerts are already turned off.</p>
            ) : (
              <button className="login-button" onClick={() => void confirmUnsubscribe()} disabled={submitting}>
                {submitting ? "Updating..." : "Turn Off These Alerts"}
              </button>
            )}
          </>
        )}
        {unsubscribed && (
          <>
            <h2>Alerts turned off</h2>
            <p>Cancellation availability emails are now disabled. You can turn them back on in Notification Preferences after signing in.</p>
          </>
        )}
        {!loading && <AppLink href="/" className="login-link-button">Return to Cabin Booking</AppLink>}
      </div>
    </div>
  );
}
