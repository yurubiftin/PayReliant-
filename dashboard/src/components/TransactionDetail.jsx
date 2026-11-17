import { useEffect, useRef } from "react";
import { dateTime, money, trxId } from "../format.js";
import { CloseIcon } from "./Icons.jsx";
import StatusPill from "./StatusPill.jsx";

// The pop-up shown when you click the magnifier on a transaction row.
// Uses the browser's built-in <dialog>, which handles focus and the Esc key for us.
export default function TransactionDetail({ txn, customer, merchant, onClose }) {
  const ref = useRef(null);

  useEffect(() => {
    if (txn && !ref.current.open) ref.current.showModal();
  }, [txn]);

  if (!txn) return null;

  const rows = [
    ["Amount", `KES ${money(txn.amount)}`],
    ["Customer", customer ? `${customer.name} · ${customer.phone}` : `Customer #${txn.customer_id}`],
    ["Merchant", merchant ? `${merchant.name} · ${merchant.business_code}` : `#${txn.merchant_id}`],
    ["Created", dateTime(txn.created_at)],
    ["Processing time", txn.processing_ms != null ? `${txn.processing_ms} ms` : "—"],
    ["Duplicates blocked", txn.replay_count],
    ["Idempotency key", txn.idempotency_key],
  ];
  if (txn.failure_reason) rows.push(["Failure reason", txn.failure_reason]);

  return (
    <dialog ref={ref} className="detail" onClose={onClose} aria-labelledby="detail-title">
      <div className="detail-head">
        <div>
          <span className="eyebrow">Transaction detail</span>
          <h2 id="detail-title">{trxId(txn)}</h2>
        </div>
        <StatusPill status={txn.status} />
        <button type="button" className="icon-btn" onClick={() => ref.current.close()} aria-label="Close">
          <CloseIcon />
        </button>
      </div>

      <dl className="detail-grid">
        {rows.map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd className={label === "Idempotency key" ? "mono" : ""}>{value}</dd></div>
        ))}
      </dl>

      <h3>Ledger entries</h3>
      {txn.ledger_entries.length === 0 ? (
        <p className="muted">No ledger entries: no money moved for this transaction.</p>
      ) : (
        <table className="ledger">
          <thead><tr><th>Type</th><th>Wallet</th><th className="num">Amount (KES)</th></tr></thead>
          <tbody>
            {txn.ledger_entries.map((e) => (
              <tr key={e.entry_id}>
                <td className={e.entry_type === "DEBIT" ? "debit" : "credit"}>{e.entry_type}</td>
                <td>Wallet {e.wallet_id}</td>
                <td className="num">{e.entry_type === "DEBIT" ? "−" : "+"} {money(e.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </dialog>
  );
}
