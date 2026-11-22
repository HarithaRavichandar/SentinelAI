import { NavLink } from "react-router-dom";
import { useState } from "react";

/* ================================================================== */
/*  SVG Icon Components                                                */
/* ================================================================== */

const DashboardIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="2" width="7" height="8" rx="1.5" />
    <rect x="11" y="2" width="7" height="5" rx="1.5" />
    <rect x="2" y="12" width="7" height="6" rx="1.5" />
    <rect x="11" y="9" width="7" height="9" rx="1.5" />
  </svg>
);

const TriageIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 2L18 7v6l-8 5-8-5V7l8-5z" />
    <path d="M10 12V18" />
    <path d="M10 12L18 7" />
    <path d="M10 12L2 7" />
  </svg>
);

const LiveIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="10" cy="10" r="3" />
    <path d="M5.5 5.5a6.5 6.5 0 0 0 0 9" />
    <path d="M14.5 5.5a6.5 6.5 0 0 1 0 9" />
    <path d="M3 3a10 10 0 0 0 0 14" />
    <path d="M17 3a10 10 0 0 1 0 14" />
  </svg>
);

const ChatIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 4h14a1 1 0 011 1v8a1 1 0 01-1 1H7l-4 3V5a1 1 0 011-1z" />
    <path d="M7 8h6" />
    <path d="M7 11h4" />
  </svg>
);

const BatchIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 4h12a1 1 0 011 1v10a1 1 0 01-1 1H4a1 1 0 01-1-1V5a1 1 0 011-1z" />
    <path d="M3 8h14" />
    <path d="M3 12h14" />
    <path d="M8 8v8" />
  </svg>
);

const CollapseIcon = ({ collapsed }: { collapsed: boolean }) => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
    style={{ transform: collapsed ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s ease" }}>
    <path d="M10 3L5 8l5 5" />
  </svg>
);

/* ================================================================== */
/*  Nav Items Config                                                   */
/* ================================================================== */

const NAV_ITEMS = [
  { to: "/", icon: DashboardIcon, label: "Dashboard", end: true },
  { to: "/triage", icon: TriageIcon, label: "Alert Triage" },
  { to: "/live", icon: LiveIcon, label: "Live Capture" },
  { to: "/chat", icon: ChatIcon, label: "Laya Chat" },
  { to: "/batch", icon: BatchIcon, label: "Batch Upload" },
];

/* ================================================================== */
/*  Sidebar Component                                                  */
/* ================================================================== */

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className="sidebar"
      style={{
        width: collapsed ? "64px" : "240px",
        minWidth: collapsed ? "64px" : "240px",
        transition: "width 0.25s ease, min-width 0.25s ease",
      }}
    >
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-logo">
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <rect width="28" height="28" rx="8" fill="#3b82f6" fillOpacity="0.15" />
            <path d="M14 6L20 10v8l-6 4-6-4v-8l6-4z" stroke="#3b82f6" strokeWidth="1.5" fill="none" />
            <circle cx="14" cy="14" r="2.5" fill="#3b82f6" />
          </svg>
        </div>
        {!collapsed && (
          <div className="sidebar-brand-text">
            <span className="sidebar-title">SentinelAI</span>
            <span className="sidebar-subtitle">Network Defense</span>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `sidebar-link${isActive ? " sidebar-link-active" : ""}`
            }
            title={collapsed ? item.label : undefined}
          >
            <span className="sidebar-icon">
              <item.icon />
            </span>
            {!collapsed && <span className="sidebar-label">{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        {!collapsed && (
          <div className="sidebar-status">
            <span className="sidebar-status-dot" />
            <span className="sidebar-status-text">System Online</span>
          </div>
        )}
        <button
          className="sidebar-collapse-btn"
          onClick={() => setCollapsed((c) => !c)}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <CollapseIcon collapsed={collapsed} />
        </button>
      </div>
    </aside>
  );
}