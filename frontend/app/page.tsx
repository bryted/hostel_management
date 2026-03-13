import { redirect } from "next/navigation";

import { getCurrentUser } from "../lib/server-api";

export default async function HomePage() {
  const user = await getCurrentUser();
  redirect(user ? (user.is_admin ? "/dashboard" : "/billing") : "/login");
}
