import { useState } from "react";
import { api } from "../api.js";
import PageHeader from "../components/PageHeader.jsx";
import { money } from "../format.js";
import { usePolling } from "../hooks/usePolling.js";

// Admin only: onboard merchants (with their dashboard login) and customers, and suspend/re-activate them.
// Proposal 3.1.2: "creation and management of simulated customer / merchant accounts".

const load = async () => {
  const [merchants, customers, wallets] = await Promise.all([api.merchants(), api.customers(), api.wallets()]);
  const balance = (type, id) => wallets.find((w) => w.owner_type === type && w.owner_id === id)?.balance;
  return { merchants, customers, balance };
};

export default function Accounts() {
  const { data, error, updatedAt, reload } = usePolling(load, 5000);

  return (
    <>
      <PageHeader title="Accounts" subtitle="Onboard and manage simulated merchants and customers."
                  updatedAt={updatedAt} error={error} />
      <MerchantsCard data={data} reload={reload} />
      <CustomersCard data={data} reload={reload} />
    </>
  );
}

function StatusButton({ status, onToggle }) {
  const [busy, setBusy] = useState(false);
  const suspend = status === "ACTIVE";
  return (
    <button type="button" className={suspend ? "btn-small danger" : "btn-small"} disabled={busy}
            onClick={async () => { setBusy(true); try { await onToggle(suspend ? "SUSPENDED" : "ACTIVE"); } finally { setBusy(false); } }}>
      {suspend ? "Suspend" : "Activate"}
    </button>
  );
}

const AccountStatus = ({ status }) => (
  <span className={`pill ${status === "ACTIVE" ? "pill-successful" : "pill-failed"}`}>
    {status === "ACTIVE" ? "Active" : "Suspended"}
  </span>
);

/* A small form that shows the API's validation message if something is wrong. */
function useForm(initial, submit, validate = () => null) {
  const [values, setValues] = useState(initial);
  const [message, setMessage] = useState(null); // { ok: bool, text }
  const [busy, setBusy] = useState(false);
  const field = (name) => ({
    value: values[name],
    onChange: (e) => { setValues({ ...values, [name]: e.target.value }); setMessage(null); },
  });
  async function onSubmit(e) {
    e.preventDefault();
    if (Object.values(values).some((v) => String(v).trim() === "")) {
      setMessage({ ok: false, text: "Fill in every field." });
      return;
    }
    const problem = validate(values);
    if (problem) {
      setMessage({ ok: false, text: problem });
      return;
    }
    setBusy(true);
    try {
      const text = await submit(values);
      setValues(initial);
      setMessage({ ok: true, text });
    } catch (err) {
      setMessage({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  }
  return { field, onSubmit, message, busy };
}

function FormMessage({ message }) {
  if (!message) return null;
  return <p className={message.ok ? "form-ok" : "form-error"} role={message.ok ? "status" : "alert"}>{message.text}</p>;
}

function MerchantsCard({ data, reload }) {
  const form = useForm({ name: "", business_code: "", username: "", password: "" }, async (v) => {
    const m = await api.createMerchant(v);
    reload();
    return `${m.name} onboarded. They can now sign in as "${m.login_username}".`;
  }, (v) => {
    if (!/^\d{5}$/.test(v.business_code)) return "Business code must be exactly 5 digits, e.g. 52014.";
    if (!/^[a-z0-9_]{3,30}$/.test(v.username)) return "Username: 3–30 lowercase letters, digits or _ (no spaces).";
    if (v.password.length < 8) return "Password must be at least 8 characters.";
    return null;
  });

  return (
    <section className="card panel" aria-labelledby="merchants-title">
      <h2 id="merchants-title">Merchants</h2>
      <p className="panel-sub">Each merchant has a wallet and a dashboard login that shows only their own transactions.</p>
      <div className="table-scroll">
        <table className="txn-table">
          <thead><tr><th>Name</th><th>Business code</th><th>Login</th><th className="num">Wallet (KES)</th><th>Status</th><th className="center">Action</th></tr></thead>
          <tbody>
            {(data?.merchants ?? []).map((m) => (
              <tr key={m.merchant_id}>
                <td>{m.name}</td>
                <td className="mono">{m.business_code}</td>
                <td className="mono">{m.login_username ?? "—"}</td>
                <td className="num">{money(data.balance("MERCHANT", m.merchant_id) ?? 0)}</td>
                <td><AccountStatus status={m.status} /></td>
                <td className="center"><StatusButton status={m.status}
                  onToggle={async (s) => { await api.setMerchantStatus(m.merchant_id, s); reload(); }} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <form className="inline-form" onSubmit={form.onSubmit} noValidate>
        <h3>Onboard a merchant</h3>
        <div className="form-grid">
          <label className="field">Business name<input {...form.field("name")} placeholder="Duka La Mama" /></label>
          <label className="field">Business code (5 digits)<input {...form.field("business_code")} inputMode="numeric" placeholder="52014" /></label>
          <label className="field">Login username<input {...form.field("username")} autoComplete="off" placeholder="dukalamama" /></label>
          <label className="field">Login password (min 8)<input type="password" {...form.field("password")} autoComplete="new-password" /></label>
        </div>
        <FormMessage message={form.message} />
        <button type="submit" className="btn-dark" disabled={form.busy}>{form.busy ? "Saving…" : "Add merchant"}</button>
      </form>
    </section>
  );
}

function CustomersCard({ data, reload }) {
  const form = useForm({ name: "", phone: "", initial_balance: "" }, async (v) => {
    const c = await api.createCustomer(v);
    reload();
    return `${c.name} added. They can now pay from the USSD simulator.`;
  }, (v) => {
    if (!/^254(7|1)\d{8}$/.test(v.phone)) return "Phone must be 12 digits starting 2547 or 2541, e.g. 254712000220.";
    if (!/^\d+(\.\d{1,2})?$/.test(v.initial_balance)) return "Starting balance must be an amount like 5000 or 5000.50.";
    return null;
  });

  return (
    <section className="card panel" aria-labelledby="customers-title">
      <h2 id="customers-title">Customers</h2>
      <p className="panel-sub">Simulated mobile-money users who pay merchants through the USSD simulator.</p>
      <div className="table-scroll">
        <table className="txn-table">
          <thead><tr><th>Name</th><th>Phone</th><th className="num">Wallet (KES)</th><th>Status</th><th className="center">Action</th></tr></thead>
          <tbody>
            {(data?.customers ?? []).map((c) => (
              <tr key={c.customer_id}>
                <td>{c.name}</td>
                <td className="mono">{c.phone}</td>
                <td className="num">{money(data.balance("CUSTOMER", c.customer_id) ?? 0)}</td>
                <td><AccountStatus status={c.status} /></td>
                <td className="center"><StatusButton status={c.status}
                  onToggle={async (s) => { await api.setCustomerStatus(c.customer_id, s); reload(); }} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <form className="inline-form" onSubmit={form.onSubmit} noValidate>
        <h3>Add a customer</h3>
        <div className="form-grid">
          <label className="field">Name<input {...form.field("name")} placeholder="Wanjiku M." /></label>
          <label className="field">Phone (254…)<input {...form.field("phone")} inputMode="numeric" placeholder="254712000220" /></label>
          <label className="field">Starting balance (KES)<input {...form.field("initial_balance")} inputMode="decimal" placeholder="5000.00" /></label>
        </div>
        <FormMessage message={form.message} />
        <button type="submit" className="btn-dark" disabled={form.busy}>{form.busy ? "Saving…" : "Add customer"}</button>
      </form>
    </section>
  );
}
