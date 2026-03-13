"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { storeFlashMessage } from "../lib/action-feedback";
import { logout } from "../lib/client-api";

export function LogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function handleLogout() {
    try {
      setPending(true);
      await logout();
      storeFlashMessage({
        tone: "success",
        message: "Signed out successfully.",
      });
      router.push("/login");
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <button className="button ghost" onClick={handleLogout} disabled={pending}>
      {pending ? "Signing out..." : "Sign out"}
    </button>
  );
}
