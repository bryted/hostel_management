"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type LinkItem = {
  href: string;
  label: string;
};

type Section = {
  title: string;
  links: LinkItem[];
};

type Props = {
  sections: Section[];
};

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppNav({ sections }: Props) {
  const pathname = usePathname();

  return (
    <div className="sidebar-sections">
      {sections.map((section) => (
        <section key={section.title} className="sidebar-section">
          <span className="sidebar-label">{section.title}</span>
          <div className="sidebar-links">
            {section.links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={`sidebar-link ${isActive(pathname, link.href) ? "active" : ""}`}
              >
                <strong>{link.label}</strong>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
