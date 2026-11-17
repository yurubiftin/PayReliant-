import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

// The login page. There is no "sign up": merchants are onboarded by the admin (Accounts page),
// as with a real payment provider.
export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    if (!username.trim() || !password) {
      setError("Enter your username and password.");
      return;
    }
    setBusy(true);
    try {
      await login(username.trim(), password);
      navigate(location.state?.from || "/", { replace: true });
    } catch (err) {
      setError(err.message === "Failed to fetch"
        ? "Can't reach the PayReliant API. Is the backend running?"
        : err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={onSubmit} noValidate>
        <div className="login-brand">PayReliant</div>
        <h1>Sign in</h1>
        <p className="subtitle">Merchant and admin access to the payment reliability sandbox.</p>

        <label className="field">
          Username
          <input value={username} onChange={(e) => { setUsername(e.target.value); setError(""); }}
                 autoComplete="username" autoFocus />
        </label>
        <label className="field">
          Password
          <input type="password" value={password} onChange={(e) => { setPassword(e.target.value); setError(""); }}
                 autoComplete="current-password" />
        </label>

        {error && <p className="form-error" role="alert">{error}</p>}

        <button type="submit" className="btn-dark btn-block" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="login-note">No account? Merchant accounts are created by the sandbox administrator.</p>
      </form>
    </div>
  );
}
