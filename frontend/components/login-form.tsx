"use client";

import Link from "next/link";
import { useState } from "react";

import { storeFlashMessage } from "../lib/action-feedback";
import { login } from "../lib/client-api";

export function LoginForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const user = await login(username, password);
      storeFlashMessage({
        tone: "success",
        message: `Signed in as ${user.full_name}.`,
      });
      window.location.assign(user.is_admin ? "/dashboard" : "/billing");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
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
          placeholder="admin or user@example.com"
          autoComplete="username"
          required
        />
      </label>
      <label className="field">
        <span>Password</span>
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          required
        />
      </label>
      {error ? <p className="error-text">{error}</p> : null}
      <button className="button" type="submit" disabled={pending}>
        {pending ? "Signing in..." : "Sign in"}
      </button>
      <Link className="button ghost" href="/reset-password">
        Forgot password
      </Link>
    </form>
  );
}
