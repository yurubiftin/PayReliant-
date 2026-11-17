import { Link } from "react-router-dom";
import { api } from "../api.js";
import Donut from "../components/Donut.jsx";
import PageHeader from "../components/PageHeader.jsx";
import { count, money, statusLabel, trxId } from "../format.js";
import { usePolling } from "../hooks/usePolling.js";
import { useAuth } from "../auth.jsx";

// Loads the headline stats and the 5 newest transactions together, every 3 seconds.
const load = async () => {
  const [stats, recent] = await Promise.all([api.stats(), api.transactions(5)]);
  return { stats, recent };
};

export default function Dashboard() {
  const { user, isAdmin } = useAuth();
  const { data, error, updatedAt } = usePolling(load);
  const s = data?.stats;
  const recent = data?.recent ?? [];

  // Each card: label, big value, and a short note underneath (green = good, red = needs attention).
  const cards = s ? [
    {
      label: "Total Transactions",
      value: count(s.total_transactions),
      note: `${count(s.duplicates_blocked)} duplicate request${s.duplicates_blocked === 1 ? "" : "s"} blocked`,
      tone: "good",
    },
    {
      label: "Successful Payments",
      value: s.success_rate == null ? "—" : `${s.success_rate}%`,
      note: s.success_rate == null ? "No payments yet" : s.success_rate >= 95 ? "Healthy success rate" : "Below 95% target",
      tone: s.success_rate == null || s.success_rate >= 95 ? "good" : "bad",
    },
    {
      label: "Failed Transactions",
      value: count(s.failed),
      note: s.failed > 0 ? "Requires monitoring" : "None so far",
      tone: s.failed > 0 ? "bad" : "good",
    },
    {
      label: "Average Response Time",
      value: s.avg_processing_ms == null ? "—" : `${Math.round(s.avg_processing_ms)} ms`,
      note: s.avg_processing_ms == null ? "No payments yet" : s.avg_processing_ms <= 500 ? "Within target range" : "Above 500 ms target",
      tone: s.avg_processing_ms == null || s.avg_processing_ms <= 500 ? "good" : "bad",
    },
  ] : [];

  return (
    <>
      <PageHeader
        title="Dashboard Overview"
        subtitle={isAdmin
          ? "Monitor simulated payments and transaction reliability."
          : `${user.merchant_name}: your payments and their reliability.`}
        updatedAt={updatedAt}
        error={error}
      />

      <section className="kpis" aria-label="Key figures">
        {(s ? cards : Array.from({ length: 4 }, (_, i) => ({ label: "…", value: "…", note: "", key: i })))
          .map((c) => (
            <div className="card kpi" key={c.label + (c.key ?? "")}>
              <span className="kpi-label">{c.label}</span>
              <span className="kpi-value">{c.value}</span>
              <span className={`kpi-note ${c.tone}`}>{c.note}</span>
            </div>
          ))}
      </section>

      <section className="split">
        <div className="card panel">
          <h2>Payment Outcomes</h2>
          <p className="panel-sub">Distribution of simulated transactions</p>
          <div className="outcomes">
            <Donut
              slices={[
                { label: "Successful", value: s?.successful ?? 0, color: "var(--green)" },
                { label: "Failed", value: s?.failed ?? 0, color: "var(--red)" },
                { label: "Pending", value: s?.pending ?? 0, color: "var(--grey)" },
              ]}
              centerValue={s?.success_rate == null ? "—" : `${s.success_rate}%`}
              centerLabel="Successful"
            />
            <ul className="legend">
              <li><span className="swatch" style={{ background: "var(--green)" }} />Successful <b>{count(s?.successful ?? 0)}</b></li>
              <li><span className="swatch" style={{ background: "var(--red)" }} />Failed <b>{count(s?.failed ?? 0)}</b></li>
              <li><span className="swatch" style={{ background: "var(--grey)" }} />Pending <b>{count(s?.pending ?? 0)}</b></li>
            </ul>
          </div>
          {s && (
            <p className="panel-foot">
              KES {money(s.volume_successful)} moved ·{" "}
              <span className={s.ledger_balanced ? "good" : "bad"}>
                {s.ledger_balanced ? "Ledger balanced (debits = credits)" : "Ledger NOT balanced"}
              </span>
            </p>
          )}
        </div>

        <div className="card panel">
          <div className="panel-head">
            <div>
              <h2>Recent Transactions</h2>
              <p className="panel-sub">Latest simulated activity</p>
            </div>
            <Link to="/transactions" className="link">View all</Link>
          </div>
          {recent.length === 0 ? (
            <p className="muted">No transactions yet. Make a payment in the USSD simulator.</p>
          ) : (
            <ul className="recent">
              {recent.map((t) => (
                <li key={t.transaction_id}>
                  <span className="mono">{trxId(t)}</span>
                  <span className="recent-amount">KES {money(t.amount)}</span>
                  <span className={`status-text ${t.status.toLowerCase()}`}>{statusLabel[t.status]}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </>
  );
}
