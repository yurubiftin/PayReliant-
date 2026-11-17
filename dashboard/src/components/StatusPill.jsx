import { statusLabel } from "../format.js";

// The coloured status badge used in tables: green Successful, red Failed, amber Pending/Processing.
export default function StatusPill({ status }) {
  return <span className={`pill pill-${status.toLowerCase()}`}>{statusLabel[status] || status}</span>;
}
