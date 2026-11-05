import { useState, useEffect, type FormEvent } from "react";
import { invitationsApi, type InvitationTokenInfo } from "../api/invitations";

interface AcceptInvitationProps {
  token: string;
  onAccepted: () => void;
}

export function AcceptInvitation({ token, onAccepted }: AcceptInvitationProps) {
  const [tokenInfo, setTokenInfo] = useState<InvitationTokenInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    invitationsApi.validate(token, controller.signal)
      .then((data) => {
        if (data.valid) {
          setTokenInfo(data);
          setEmail(data.email || "");
          setFirstName(data.first_name || "");
          setLastName(data.last_name || "");
          setPhone(data.phone_number || "");
        } else {
          setTokenInfo({ valid: false });
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setTokenInfo({ valid: false });
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      await invitationsApi.accept({
        token,
        first_name: firstName,
        last_name: lastName,
        email,
        phone_number: phone || null,
      });
      onAccepted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="spinner" />
        </div>
      </div>
    );
  }

  if (!tokenInfo?.valid) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="login-badge">
            <div className="badge-border">
              <h1>Cabin Booking</h1>
            </div>
          </div>
          <div className="invite-error-message">
            This invitation link is invalid or has expired. Please contact your family administrator for a new invitation.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-badge">
          <div className="badge-border">
            <svg className="login-mountain-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 20L8 10l4 6 4-10 5 14H3z" />
            </svg>
            <h1>Cabin Booking</h1>
            <p className="invite-welcome-text">
              Welcome to the {tokenInfo.share_name || "Family"} share! You'll use this email to sign in each time you need to {tokenInfo.is_viewer ? "view the reservation calendar." : "make a reservation."}
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="invite-form-row">
            <input
              type="text"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              placeholder="First Name"
              className="login-input"
              disabled={submitting}
              required
              autoFocus
            />
            <input
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              placeholder="Last Name"
              className="login-input"
              disabled={submitting}
              required
            />
          </div>

          <input
            type="email"
            value={email}
            placeholder="Email"
            className="login-input"
            disabled
          />

          <input
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="Phone (optional)"
            className="login-input"
            disabled={submitting}
          />

          {error && <p className="login-error">{error}</p>}

          <button type="submit" className="login-button" disabled={submitting}>
            {submitting ? "CREATING ACCOUNT..." : "CONTINUE"}
          </button>
        </form>
      </div>
    </div>
  );
}
