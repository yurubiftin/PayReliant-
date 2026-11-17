import { API_URL } from "../api.js";

// Page title + subtitle (as in the Figma), plus a "Live" badge showing when data last refreshed,
// and a clear message if the API can't be reached.
export default function PageHeader({ title, subtitle, updatedAt, error, children }) {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>{title}</h1>
          <p className="subtitle">{subtitle}</p>
        </div>
        <div className="page-head-right">
          {children}
          {updatedAt && !error && (
            <span className="live" title="Refreshes every 3 seconds">
              <span className="dot" aria-hidden="true" /> Live · {updatedAt.toLocaleTimeString("en-GB")}
            </span>
          )}
        </div>
      </div>
      {error && (
        <div className="banner" role="alert">
          Can't reach the PayReliant API at <code>{API_URL}</code>. Is the backend running
          (<code>uvicorn app.main:app --reload</code>) and Docker started?
        </div>
      )}
    </>
  );
}
