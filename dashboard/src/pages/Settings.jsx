import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import PageHeader from "../components/PageHeader.jsx";
import { dateTime } from "../format.js";

// Settings (Figma page 5). Unlike the prototype, every control here really changes the sandbox:
// the USSD simulator, the reliability tests and real payments all read these values.

const FIELDS = {
  provider_name:         { label: "Default Network / Provider", hint: "Shown on the USSD simulator's menu." },
  client_timeout_s:      { label: "Default Transaction Timeout (seconds)", hint: "How long a client waits for a reply before retrying.", min: 0.1, max: 10, step: 0.1 },
  max_requests_per_test: { label: "Maximum Requests per Test", hint: "How many requests each reliability test sends (10–500).", min: 10, max: 500, step: 10 },
  retry_attempts:        { label: "Retry Attempts", hint: "How many times a client retries after a timeout (0–10).", min: 0, max: 10, step: 1 },
  failure_rate_pct:      { label: "Failure rate (%)", hint: "This share of real payments fails ON PURPOSE after the debit, to prove the rollback.", min: 0, max: 100, step: 1 },
  added_latency_ms:      { label: "Added latency (ms)", hint: "Extra delay added to every real payment (0–5000).", min: 0, max: 5000, step: 50 },
};

export default function Settings() {
  const { user } = useAuth();
  const [saved, setSaved] = useState(null);     // settings as stored by the API
  const [form, setForm] = useState(null);       // what's on screen
  const [loadError, setLoadError] = useState(null);
  const [message, setMessage] = useState(null); // { ok, text }
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.settings().then((s) => { setSaved(s); setForm(s); }).catch(setLoadError);
  }, []);

  const set = (name, value) => { setForm({ ...form, [name]: value }); setMessage(null); };
  const changed = saved && form && Object.keys(FIELDS).concat("session_logging").some((k) => String(form[k]) !== String(saved[k]));

  function problem() {
    if (String(form.provider_name).trim().length < 2) return "Provider name needs at least 2 characters.";
    for (const [name, f] of Object.entries(FIELDS)) {
      if (f.min === undefined) continue;
      const n = Number(form[name]);
      if (String(form[name]).trim() === "" || Number.isNaN(n) || n < f.min || n > f.max)
        return `${f.label}: enter a number from ${f.min} to ${f.max}.`;
    }
    return null;
  }

  async function save(e) {
    e.preventDefault();
    const p = problem();
    if (p) { setMessage({ ok: false, text: p }); return; }
    setBusy(true);
    try {
      const body = {
        provider_name: form.provider_name.trim(),
        session_logging: form.session_logging,
        client_timeout_s: Number(form.client_timeout_s),
        max_requests_per_test: Math.round(Number(form.max_requests_per_test)),
        retry_attempts: Math.round(Number(form.retry_attempts)),
        failure_rate_pct: Number(form.failure_rate_pct),
        added_latency_ms: Math.round(Number(form.added_latency_ms)),
      };
      const s = await api.saveSettings(body);
      setSaved(s); setForm(s);
      setMessage({ ok: true, text: "Settings saved. They apply straight away." });
    } catch (err) {
      setMessage({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  }

  const input = (name) => {
    const f = FIELDS[name];
    return (
      <label className="field">
        {f.label}
        <input value={form[name]} onChange={(e) => set(name, e.target.value)}
               {...(f.min !== undefined ? { type: "number", min: f.min, max: f.max, step: f.step, inputMode: "decimal" } : {})} />
        <span className="hint">{f.hint}</span>
      </label>
    );
  };

  const injecting = form && (Number(form.failure_rate_pct) > 0 || Number(form.added_latency_ms) > 0);

  return (
    <>
      <PageHeader title="Settings" subtitle="Manage your sandbox preferences and account settings." error={loadError} />
      {form && (
        <form className="settings" onSubmit={save} noValidate>
          <section className="card panel" aria-labelledby="sim-title">
            <h2 id="sim-title">Simulation Preferences</h2>
            <p className="panel-sub">Configure default values for simulated payment sessions.</p>
            <div className="form-grid two">
              {input("provider_name")}
              {input("client_timeout_s")}
              <label className="field">
                Default Currency
                <input value="KES — Kenyan Shilling" readOnly aria-readonly="true" />
                <span className="hint">Fixed: the sandbox simulates Kenyan mobile money.</span>
              </label>
              <label className="field">
                Session Logging
                <select value={form.session_logging ? "on" : "off"} onChange={(e) => set("session_logging", e.target.value === "on")}>
                  <option value="on">Enabled</option>
                  <option value="off">Disabled</option>
                </select>
                <span className="hint">When enabled, the API terminal prints one line per payment.</span>
              </label>
            </div>
          </section>

          <section className="card panel" aria-labelledby="rel-title">
            <h2 id="rel-title">Reliability Configuration</h2>
            <p className="panel-sub">Set limits for safe testing in the simulated environment.</p>
            <div className="form-grid two">
              {input("max_requests_per_test")}
              {input("retry_attempts")}
            </div>
          </section>

          <section className={`card panel ${injecting ? "warn-card" : ""}`} aria-labelledby="inj-title">
            <h2 id="inj-title">Failure Injection</h2>
            <p className="panel-sub">
              Make <b>real</b> payments (USSD simulator, API) fail or slow down on purpose, then watch the dashboard:
              failed payments must move no money. Set both back to 0 when you're done.
            </p>
            <div className="form-grid two">
              {input("failure_rate_pct")}
              {input("added_latency_ms")}
            </div>
            {injecting && <p className="form-error" role="status">Failure injection is ON: real payments are affected.</p>}
          </section>

          <section className="card panel account-row" aria-labelledby="acc-title">
            <div>
              <h2 id="acc-title">Account</h2>
              <p className="panel-sub">
                PayReliant Sandbox · Demo environment only · signed in as <b>{user.username}</b>
                {saved.updated_at && <> · last saved {dateTime(saved.updated_at)}</>}
              </p>
            </div>
            <div className="account-actions">
              <button type="submit" className="btn-dark" disabled={busy || !changed}>{busy ? "Saving…" : "Save Changes"}</button>
            </div>
          </section>
          {message && <p className={message.ok ? "form-ok" : "form-error"} role={message.ok ? "status" : "alert"}>{message.text}</p>}
        </form>
      )}
    </>
  );
}
