import { useState, useEffect, useRef } from "react";
import { authApi } from "../api/auth";
import { navigateTo } from "../routing";
import { createSingleFlightTask } from "../utils/singleFlight";

interface VerifyMagicLinkProps {
  token: string;
  nextPath?: string | null;
  onVerified: () => void;
}

export function VerifyMagicLink({ token, nextPath, onVerified }: VerifyMagicLinkProps) {
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(true);
  const onVerifiedRef = useRef(onVerified);
  onVerifiedRef.current = onVerified;
  const verificationRef = useRef<{
    token: string;
    run: () => Promise<void>;
  } | null>(null);

  if (verificationRef.current?.token !== token) {
    verificationRef.current = {
      token,
      run: createSingleFlightTask(async () => {
        await authApi.verifyMagicLink(token);
      }),
    };
  }

  useEffect(() => {
    let active = true;
    const runVerification = verificationRef.current!.run;

    void runVerification()
      .then(() => {
        if (active) onVerifiedRef.current();
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      })
      .finally(() => {
        if (active) setVerifying(false);
      });

    return () => {
      active = false;
    };
  }, [token]);

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-badge">
          <div className="badge-border">
            <svg className="login-mountain-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 20L8 10l4 6 4-10 5 14H3z" />
            </svg>
            <h1>Cabin Booking</h1>
          </div>
        </div>

        {verifying ? (
          <div className="magic-link-status">
            <div className="spinner" style={{ margin: "0 auto 1rem" }} />
            <p style={{ color: "var(--text-muted)" }}>
              {nextPath?.startsWith("/booking/pay") ? "Opening your payment link..." : "Signing you in..."}
            </p>
          </div>
        ) : error ? (
          <div className="magic-link-status">
            <p className="login-error" style={{ margin: "0 0 1.5rem" }}>{error}</p>
            <a
              href="/"
              className="login-link-button"
              onClick={(e) => {
                e.preventDefault();
                navigateTo("/", { replace: true });
              }}
            >
              Back to Login
            </a>
          </div>
        ) : null}
      </div>
    </div>
  );
}
