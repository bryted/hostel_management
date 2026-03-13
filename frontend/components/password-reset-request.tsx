"use client";

import { useState } from "react";

import type { PasswordResetRequestResponse } from "../lib/api";
import { storeFlashMessage } from "../lib/action-feedback";
import { postJson } from "../lib/client-api";

export function PasswordResetRequest() {
  const [username, setUsername] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [devToken, setDevToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    setDevToken(null);
    setError(null);
    try {
      const response = await postJson<PasswordResetRequestResponse, { username: string }>(
        "/auth/password-reset/request",
        { username },
      );
      setMessage(response.message);
      storeFlashMessage({ tone: "success", message: response.message });
      setDevToken(response.reset_token ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset request failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="stack" onSubmit={handleSubmit}>
      <label className="field">
        <span>Username or email</span>
        <input
          type="text"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
          required
        />
      </label>
      {message ? <p className="success-text">{message}</p> : null}
      {devToken ? <p className="section-note">Mock reset token: {devToken}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
      <button className="button" disabled={pending} type="submit">
        {pending ? "Preparing..." : "Request reset"}
      </button>
    </form>
  );
}
