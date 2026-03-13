"use client";

import Link from "next/link";
import { useState } from "react";

import type { ActionResponse } from "../lib/api";
import { storeFlashMessage } from "../lib/action-feedback";
import { postJson } from "../lib/client-api";

type Props = {
  token: string;
};

export function PasswordResetForm({ token }: Props) {
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    setError(null);
    try {
      const response = await postJson<ActionResponse, { token: string; password: string }>(
        "/auth/password-reset/confirm",
        { token, password },
      );
      setMessage(response.message);
      storeFlashMessage({ tone: "success", message: response.message });
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="stack" onSubmit={handleSubmit}>
      <label className="field">
        <span>New password</span>
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="new-password"
          required
        />
      </label>
      {message ? <p className="success-text">{message}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
      <button className="button" disabled={pending} type="submit">
        {pending ? "Resetting..." : "Reset password"}
      </button>
      <Link className="button ghost" href="/login">
        Back to login
      </Link>
    </form>
  );
}
