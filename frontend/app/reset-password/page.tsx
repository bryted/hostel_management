import { PasswordResetForm } from "../../components/password-reset-form";
import { PasswordResetRequest } from "../../components/password-reset-request";

type PageProps = {
  searchParams: Promise<{ token?: string }>;
};

export default async function ResetPasswordPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const token = params.token ?? "";

  return (
    <div className="login-shell">
      <section className="panel narrow auth-card">
        <div className="auth-copy">
          <h1>{token ? "Reset password" : "Password reset"}</h1>
          <p>
            {token
              ? "Choose a new password for your account."
              : "Request a reset link. If email delivery is offline, ask an admin to reset your password from Settings."}
          </p>
        </div>
        {token ? <PasswordResetForm token={token} /> : <PasswordResetRequest />}
      </section>
    </div>
  );
}
