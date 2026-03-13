import type { Metadata } from "next";

import { AppNav } from "../components/app-nav";
import { GlobalFlash } from "../components/global-flash";
import { GlobalSearch } from "../components/global-search";
import { LogoutButton } from "../components/logout-button";
import { getCurrentUser } from "../lib/server-api";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hostel Ops",
  description: "Modern admin panel for hostel operations.",
};

function getSections(isAdmin: boolean | null) {
  if (isAdmin) {
    return [
      {
        title: "Command",
        links: [
          { href: "/dashboard", label: "Dashboard" },
          { href: "/onboarding", label: "Onboarding" },
          { href: "/billing", label: "Billing" },
        ],
      },
      {
        title: "Operations",
        links: [
          { href: "/tenants", label: "Tenants" },
          { href: "/beds", label: "Beds" },
          { href: "/allocations", label: "Allocations" },
          { href: "/inventory", label: "Inventory" },
        ],
      },
      {
        title: "Admin",
        links: [
          { href: "/reports", label: "Reports" },
          { href: "/settings", label: "Settings" },
        ],
      },
    ];
  }
  return [
    {
      title: "Cashier",
      links: [
        { href: "/billing", label: "Billing" },
        { href: "/dashboard", label: "Dashboard" },
        { href: "/tenants", label: "Tenants" },
        { href: "/beds", label: "Beds" },
      ],
    },
  ];
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const user = await getCurrentUser();

  if (!user) {
    return (
      <html lang="en">
        <body>
          <div className="auth-frame">
            <main className="auth-main">
              <GlobalFlash />
              {children}
            </main>
          </div>
        </body>
      </html>
    );
  }

  const sections = getSections(user.is_admin);

  return (
    <html lang="en">
      <body>
        <div className="app-frame">
          <aside className="sidebar">
            <div className="sidebar-brand">
              <div className="sidebar-brand-mark">HO</div>
              <div className="sidebar-brand-copy">
                <h1>Hostel Ops</h1>
                <span>{user.is_admin ? "Admin panel" : "Cashier desk"}</span>
              </div>
            </div>
            <AppNav sections={sections} />
            <div className="sidebar-footer">
              <div className="session-card">
                <div className="session-copy">
                  <strong>{user.full_name}</strong>
                  <span>{user.is_admin ? "Admin account" : "Cashier account"}</span>
                </div>
                <LogoutButton />
              </div>
            </div>
          </aside>
          <div className="app-main">
            <div className="app-topbar">
              <GlobalSearch isAdmin={user.is_admin} />
              <div className="topbar-status">
                <span>{user.is_admin ? "Admin" : "Cashier"}</span>
              </div>
            </div>
            <main className="page-stack">
              <GlobalFlash />
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
