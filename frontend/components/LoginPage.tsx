import { useState, useEffect, useRef, type FormEvent } from "react";
import cabinLogo from "../logo.svg";

type LoginView = "magic-link" | "check-email" | "password";

interface LoginPageProps {
  onLogin: (email: string, password: string) => Promise<boolean>;
  onSendMagicLink: (email: string) => Promise<boolean>;
  error: string | null;
  isLoading: boolean;
}

export function LoginPage({ onLogin, onSendMagicLink, error, isLoading }: LoginPageProps) {
  const [view, setView] = useState<LoginView>("magic-link");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [sending, setSending] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const cooldownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (cooldownRef.current) clearInterval(cooldownRef.current);
    };
  }, []);

  const startCooldown = () => {
    setResendCooldown(60);
    if (cooldownRef.current) clearInterval(cooldownRef.current);
    cooldownRef.current = setInterval(() => {
      setResendCooldown((prev) => {
        if (prev <= 1) {
          if (cooldownRef.current) clearInterval(cooldownRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  const handleSendMagicLink = async (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    setSending(true);
    await onSendMagicLink(email);
    setSending(false);
    startCooldown();
    setView("check-email");
  };

  const handleResend = async () => {
    if (resendCooldown > 0 || !email.trim()) return;
    setSending(true);
    await onSendMagicLink(email);
    setSending(false);
    startCooldown();
  };

  const handlePasswordLogin = async (e: FormEvent) => {
    e.preventDefault();
    // Keep email autocomplete-friendly while leaving password autocomplete disabled by request.
    if (email.trim() && password.trim()) {
      await onLogin(email, password);
    }
  };

  const badge = (
    <div className="login-badge">
      <img src={cabinLogo} alt="Cabin Booking - Demo" className="login-logo" />
    </div>
  );

  if (view === "check-email") {
    return (
      <div className="login-page">
        <div className="login-card">
          {badge}

          <div className="magic-link-status">
            <div className="check-email-heading">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: "var(--selected-color)" }}>
                <rect x="2" y="4" width="20" height="16" rx="2" />
                <polyline points="22,4 12,13 2,4" />
              </svg>
              <h2>Check your email</h2>
            </div>
            <p className="check-email-subtext">
              We sent a sign-in link to <strong>{email}</strong>
            </p>

            <button
              className="login-button secondary"
              onClick={handleResend}
              disabled={sending || resendCooldown > 0}
            >
              {sending ? "SENDING..." : resendCooldown > 0 ? `RESEND LINK (${resendCooldown}s)` : "RESEND LINK"}
            </button>

            <div className="login-links">
              <button
                className="login-link-button"
                onClick={() => { setEmail(""); setView("magic-link"); }}
              >
                Try a different email
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (view === "password") {
    return (
      <div className="login-page">
        <div className="login-card">
          {badge}

          <form onSubmit={handlePasswordLogin} autoComplete="on">
            <input
              id="login-email"
              name="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value.toLowerCase())}
              placeholder="Email"
              className="login-input"
              disabled={isLoading}
              autoComplete="username"
              autoFocus
            />

            <input
              id="login-password"
              name="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="login-input"
              disabled={isLoading}
            />

            {error && <p className="login-error">{error}</p>}

            <button type="submit" className="login-button" disabled={isLoading}>
              {isLoading ? "SIGNING IN..." : "SIGN IN"}
            </button>
          </form>

          <div className="login-links">
            <button
              className="login-link-button"
              onClick={() => setView("magic-link")}
            >
              Sign in with email link instead
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Default: magic-link view
  return (
    <div className="login-page">
      <div className="login-card">
        {badge}

        <h2 className="login-heading">Login to Cabin Booking</h2>

        <form onSubmit={handleSendMagicLink} autoComplete="on">
          <input
            id="magic-link-email"
            name="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value.toLowerCase())}
            placeholder="Email"
            className="login-input"
            disabled={sending}
            autoComplete="email"
            autoFocus
          />

          <button type="submit" className="login-button" disabled={sending || !email.trim()}>
            {sending ? "SENDING..." : "SEND SIGN-IN LINK"}
          </button>
        </form>

      </div>
    </div>
  );
}
