import { useState } from "react";
import { api } from "../api.js";
import { AlertIcon, ClockIcon, CopyIcon, TrendIcon } from "../components/Icons.jsx";
import PageHeader from "../components/PageHeader.jsx";
import { dateTime } from "../format.js";
import { usePolling } from "../hooks/usePolling.js";

// Reliability Tests (Figma page 4). Each "Run test" button asks the API to fire many real payments
// through the payment logic at once, then check that every shilling is accounted for.
// These map to Table 4.6 of the proposal (scenarios 2-5).

const TESTS = [
  { id: "duplicate", title: "Duplicate Requests", Icon: CopyIcon, tone: "blue",
    text: "Check whether repeated requests are safely handled.",
    how: "Each payment is sent 5 times at the same moment. Expected: charged once." },
  { id: "timeout", title: "Timeout Simulation", Icon: ClockIcon, tone: "amber",
    text: "Simulate delayed responses from the payment service.",
    how: "The server is slower than the client's timeout, so the client retries with the same key. Expected: charged once." },
  { id: "failed", title: "Failed Payments", Icon: AlertIcon, tone: "red",
    text: "Test how the gateway responds to failed transactions.",
    how: "Payments above the balance, and payments that fail mid-way after the debit. Expected: no money moves." },
  { id: "concurrent", title: "Concurrent Requests", Icon: TrendIcon, tone: "green",
    text: "Assess system behavior under multiple requests.",
    how: "Many different payments from one wallet at once. Expected: every payment counted, no lost updates." },
];
const titleOf = Object.fromEntries(TESTS.map((t) => [t.id, t.title]));

export default function Reliability() {
  const { data: runs, error, updatedAt, reload } = usePolling(api.reliabilityRuns, 10000);
  const [running, setRunning] = useState(null);   // id of the test running now
  const [runError, setRunError] = useState(null);
  const [open, setOpen] = useState(null);         // run whose checks are shown

  async function run(id) {
    setRunning(id);
    setRunError(null);
    try {
      const result = await api.runReliabilityTest(id);
      await reload();
      setOpen(result.run_id);
    } catch (err) {
      setRunError(err.message);
    } finally {
      setRunning(null);
    }
  }

  const latest = (id) => runs?.find((r) => r.scenario === id);

  return (
    <>
      <PageHeader title="Reliability Tests" subtitle="Evaluate payment reliability under simulated failure conditions."
                  updatedAt={updatedAt} error={error} />
      {runError && <div className="banner" role="alert">{runError}</div>}

      <div className="test-grid">
        {TESTS.map(({ id, title, text, how, Icon, tone }) => {
          const last = latest(id);
          const state = running === id ? "running" : last ? last.status.toLowerCase() : "ready";
          return (
            <section key={id} className="card test-card" aria-labelledby={`t-${id}`}>
              <div className="test-head">
                <span className={`test-icon ${tone}`}><Icon /></span>
                <div>
                  <h2 id={`t-${id}`}>{title}</h2>
                  <p className="panel-sub">{text}</p>
                </div>
              </div>
              <p className="test-how">{how}</p>
              <div className="test-foot">
                <span className={`test-state ${state}`} role="status">
                  <span className="dot" aria-hidden="true" />
                  {state === "running" ? "Running…" : state === "ready" ? "Ready to test"
                    : `Last run ${last.status === "PASSED" ? "passed" : "FAILED"}: ${last.passed}/${last.requests} correct`}
                </span>
                <button type="button" className="btn-dark" disabled={running !== null} onClick={() => run(id)}>
                  {running === id ? "Running…" : "Run test"}
                </button>
              </div>
            </section>
          );
        })}
      </div>

      <section className="card panel" aria-labelledby="results-title">
        <h2 id="results-title">Recent Test Results</h2>
        <p className="panel-sub">Real results from this sandbox. Click a row to see the consistency checks behind it.</p>
        <div className="table-scroll">
          <table className="txn-table">
            <thead>
              <tr><th>Test Type</th><th className="num">Requests</th><th className="num">Passed</th><th className="num">Failed</th>
                <th className="num">Time</th><th className="num">p95</th><th>When</th><th>Status</th></tr>
            </thead>
            <tbody>
              {(runs ?? []).length === 0 && (
                <tr><td colSpan={8} className="empty">No tests run yet. Press <b>Run test</b> on any card above.</td></tr>
              )}
              {(runs ?? []).map((r) => (
                <RunRow key={r.run_id} run={r} open={open === r.run_id}
                        onToggle={() => setOpen(open === r.run_id ? null : r.run_id)} />
              ))}
            </tbody>
          </table>
        </div>
        <p className="panel-foot">
          Each test uses its own sandbox accounts (“Reliability Test Customer” → merchant 59999), so demo balances are untouched.
          Requests per test and timeout/retry values come from <b>Settings</b>.
        </p>
      </section>
    </>
  );
}

function RunRow({ run, open, onToggle }) {
  const ok = run.status === "PASSED";
  return (
    <>
      <tr className="clickable" onClick={onToggle} tabIndex={0} aria-expanded={open}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onToggle())}>
        <td>{titleOf[run.scenario] ?? run.scenario}</td>
        <td className="num">{run.requests}</td>
        <td className="num">{run.passed}</td>
        <td className={`num ${run.failed ? "bad" : ""}`}>{run.failed}</td>
        <td className="num">{(run.duration_ms / 1000).toFixed(2)} s</td>
        <td className="num">{run.p95_ms != null ? `${Math.round(run.p95_ms)} ms` : "—"}</td>
        <td>{dateTime(run.created_at)}</td>
        <td><span className={`pill ${ok ? "pill-successful" : "pill-failed"}`}>{ok ? "Passed" : "Failed"}</span></td>
      </tr>
      {open && (
        <tr className="checks-row">
          <td colSpan={8}>
            <p className="checks-summary">{run.summary}</p>
            <ul className="checks">
              {run.checks.map((c) => (
                <li key={c.name} className={c.passed ? "ok" : "bad"}>
                  <span aria-hidden="true">{c.passed ? "✓" : "✗"}</span>
                  <span className="sr-only">{c.passed ? "Passed:" : "Failed:"}</span>
                  <b>{c.name}</b> <span className="muted">{c.detail}</span>
                </li>
              ))}
            </ul>
          </td>
        </tr>
      )}
    </>
  );
}
