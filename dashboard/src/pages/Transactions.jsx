import { useMemo, useState } from "react";
import { api } from "../api.js";
import { DownloadIcon, SearchIcon } from "../components/Icons.jsx";
import PageHeader from "../components/PageHeader.jsx";
import StatusPill from "../components/StatusPill.jsx";
import TransactionDetail from "../components/TransactionDetail.jsx";
import { dateTime, money, trxId } from "../format.js";
import { usePolling } from "../hooks/usePolling.js";
import { useAuth } from "../auth.jsx";

const PAGE_SIZE = 10;

// Admins also load customer names; merchants are not allowed to list customers (privacy).
const loadFor = (isAdmin) => async () => {
  const [transactions, customers, merchants] = await Promise.all([
    api.transactions(1000), isAdmin ? api.customers() : Promise.resolve([]), api.merchants(),
  ]);
  return { transactions, customers, merchants };
};

// "2026-10-09" from a date input -> the start of that day in local time
const startOfDay = (value) => new Date(`${value}T00:00:00`);

export default function Transactions() {
  const { isAdmin } = useAuth();
  const { data, error, updatedAt } = usePolling(loadFor(isAdmin));
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("ALL");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState(null);

  const transactions = data?.transactions ?? [];
  const customers = data?.customers ?? [];
  const merchants = data?.merchants ?? [];

  // Apply the search box, status dropdown and date range to the list.
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return transactions.filter((t) => {
      if (status !== "ALL" && t.status !== status) return false;
      if (q && !trxId(t).toLowerCase().includes(q) && !t.idempotency_key.toLowerCase().includes(q)) return false;
      const created = new Date(t.created_at);
      if (from && created < startOfDay(from)) return false;
      if (to && created >= new Date(startOfDay(to).getTime() + 24 * 3600 * 1000)) return false;
      return true;
    });
  }, [transactions, search, status, from, to]);

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const visible = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const selected = transactions.find((t) => t.transaction_id === selectedId);

  // Any filter change goes back to page 1.
  const onFilter = (setter) => (e) => { setter(e.target.value); setPage(1); };

  // Download the filtered rows as a CSV file (opens in Excel).
  function exportCsv() {
    const header = ["Transaction ID", "Amount (KES)", "Status", "Date & Time", "Customer", "Merchant", "Idempotency key", "Failure reason"];
    const lines = filtered.map((t) => [
      trxId(t), t.amount, t.status, dateTime(t.created_at),
      customers.find((c) => c.customer_id === t.customer_id)?.name ?? t.customer_id,
      merchants.find((m) => m.merchant_id === t.merchant_id)?.name ?? t.merchant_id,
      t.idempotency_key, t.failure_reason ?? "",
    ]);
    const csv = [header, ...lines]
      .map((row) => row.map((v) => `"${String(v).replaceAll('"', '""')}"`).join(","))
      .join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "payreliant-transactions.csv" });
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <PageHeader
        title="Transactions"
        subtitle={isAdmin ? "View and monitor all simulated payment transactions." : "Payments received by your business."}
        updatedAt={updatedAt}
        error={error}
      />

      <div className="toolbar">
        <label className="search">
          <SearchIcon />
          <span className="sr-only">Search by transaction ID or idempotency key</span>
          <input type="search" placeholder="Search by transaction ID..." value={search} onChange={onFilter(setSearch)} />
        </label>
        <label className="sr-only" htmlFor="status">Status</label>
        <select id="status" value={status} onChange={onFilter(setStatus)}>
          <option value="ALL">All statuses</option>
          <option value="SUCCESSFUL">Successful</option>
          <option value="FAILED">Failed</option>
          <option value="PENDING">Pending</option>
          <option value="PROCESSING">Processing</option>
        </select>
        <div className="dates">
          <label>From <input type="date" value={from} onChange={onFilter(setFrom)} /></label>
          <label>To <input type="date" value={to} onChange={onFilter(setTo)} /></label>
        </div>
        <button type="button" className="btn-dark" onClick={exportCsv} disabled={!filtered.length}>
          <DownloadIcon /> Export
        </button>
      </div>

      <div className="card table-card">
        <div className="table-scroll">
          <table className="txn-table">
            <thead>
              <tr>
                <th>Transaction ID</th>
                <th className="num">Amount (KES)</th>
                <th>Status</th>
                <th>Date &amp; Time</th>
                <th className="center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((t) => (
                <tr key={t.transaction_id}>
                  <td className="mono">{trxId(t)}</td>
                  <td className="num">{money(t.amount)}</td>
                  <td><StatusPill status={t.status} /></td>
                  <td>{dateTime(t.created_at)}</td>
                  <td className="center">
                    <button type="button" className="icon-btn" onClick={() => setSelectedId(t.transaction_id)}
                            aria-label={`View details of ${trxId(t)}`}>
                      <SearchIcon />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data && visible.length === 0 && (
            <p className="muted empty-row">
              {transactions.length ? "No transactions match these filters." : "No transactions yet. Make a payment in the USSD simulator."}
            </p>
          )}
        </div>

        <div className="table-foot">
          <span>
            {filtered.length
              ? `Showing ${(current - 1) * PAGE_SIZE + 1}–${Math.min(current * PAGE_SIZE, filtered.length)} of ${filtered.length} transactions`
              : "Showing 0 transactions"}
          </span>
          <nav className="pager" aria-label="Pages">
            {Array.from({ length: pages }, (_, i) => i + 1)
              .filter((n) => n === 1 || n === pages || Math.abs(n - current) <= 1)
              .map((n) => (
                <button key={n} type="button" className={n === current ? "active" : ""}
                        aria-current={n === current ? "page" : undefined} onClick={() => setPage(n)}>
                  {n}
                </button>
              ))}
            <button type="button" onClick={() => setPage(current + 1)} disabled={current >= pages} aria-label="Next page">›</button>
          </nav>
        </div>
      </div>

      <TransactionDetail
        txn={selected}
        customer={selected && customers.find((c) => c.customer_id === selected.customer_id)}
        merchant={selected && merchants.find((m) => m.merchant_id === selected.merchant_id)}
        onClose={() => setSelectedId(null)}
      />
    </>
  );
}
