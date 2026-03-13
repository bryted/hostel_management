import { redirect } from "next/navigation";

import { LoginForm } from "../../components/login-form";
import { getCurrentUser } from "../../lib/server-api";

export default async function LoginPage() {
  const user = await getCurrentUser();
  if (user) {
    redirect(user.is_admin ? "/dashboard" : "/billing");
  }

  return (
    <div className="login-shell">
      <section className="panel narrow auth-card">
        <div className="auth-copy">
          <h1>Hostel Ops</h1>
          <p>Sign in with your username or email.</p>
        </div>
        <LoginForm />
      </section>
    </div>
  );
}
