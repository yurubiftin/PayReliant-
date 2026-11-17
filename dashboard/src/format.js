// Small helpers that turn raw API values into what the screens show.

// 1234.5 -> "1,234.50"
export const money = (value) =>
  Number(value).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// 1284 -> "1,284"
export const count = (value) => Number(value).toLocaleString("en-KE");

// Transaction 12 created on 9 Oct 2026 -> "TRX-20261009-0012" (display format from the Figma design)
export function trxId(txn) {
  const d = new Date(txn.created_at);
  const ymd = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  return `TRX-${ymd}-${String(txn.transaction_id).padStart(4, "0")}`;
}

// "2026-10-09T11:32:00Z" -> "09 Oct 2026, 14:32" (shown in the viewer's local time, e.g. Nairobi)
export function dateTime(iso) {
  const d = new Date(iso);
  const date = d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return `${date}, ${time}`;
}

// Status labels as written in the design.
export const statusLabel = {
  SUCCESSFUL: "Successful",
  FAILED: "Failed",
  PENDING: "Pending",
  PROCESSING: "Processing",
};
