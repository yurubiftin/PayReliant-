import { Link, NavLink, Outlet } from "react-router-dom";
import { API_URL } from "../api.js";
import { useAuth } from "../auth.jsx";
import {
  DashboardIcon, ExternalIcon, LogoutIcon, PhoneIcon, SearchIcon, SettingsIcon, ShieldIcon,
  TransactionsIcon, UserIcon, UsersIcon,
} from "./Icons.jsx";

// The frame around every page: dark sidebar on the left, top bar, then the page itself (<Outlet />).
// Admins see every menu item; a merchant sees only their Dashboard and Transactions.
export default function Layout() {
  const { user, isAdmin, logout } = useAuth();

  return (
    <div className="app">
      <nav className="sidebar" aria-label="Main">
        <div className="brand">PayReliant</div>
        <NavLink to="/" end className="nav-item"><DashboardIcon /> Dashboard</NavLink>
        <NavLink to="/transactions" className="nav-item"><TransactionsIcon /> Transactions</NavLink>
        {isAdmin && (
          <>
            {/* The USSD simulator is served by the API itself, so this opens it in a new tab. */}
            <a href={`${API_URL}/simulator/`} target="_blank" rel="noreferrer" className="nav-item">
              <PhoneIcon /> USSD Simulator <span className="ext"><ExternalIcon /></span>
            </a>
            <NavLink to="/reliability" className="nav-item"><ShieldIcon /> Reliability Tests</NavLink>
            <NavLink to="/accounts" className="nav-item"><UsersIcon /> Accounts</NavLink>
            <NavLink to="/settings" className="nav-item"><SettingsIcon /> Settings</NavLink>
          </>
        )}
        <p className="sidebar-note">Sandbox: simulated money only.</p>
      </nav>

      <div className="main">
        <header className="topbar">
          <Link to="/transactions" className="icon-btn" aria-label="Search transactions"><SearchIcon /></Link>
          <div className="user-chip">
            <span className="avatar" aria-hidden="true"><UserIcon /></span>
            <span className="user-text">
              <strong>{user.merchant_name || user.username}</strong>
              <span>{isAdmin ? "Administrator" : `Merchant · ${user.username}`}</span>
            </span>
          </div>
          <button type="button" className="btn-outline" onClick={logout}><LogoutIcon /> Log out</button>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
