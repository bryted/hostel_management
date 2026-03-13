"use client";

import type { ActionResponse, User } from "./api";
import { storeFlashMessage } from "./action-feedback";

async function readResponse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      typeof body?.detail === "string" ? body.detail : `Request failed: ${response.status}`;
    storeFlashMessage({ tone: "error", message: detail });
    throw new Error(detail);
  }
  return body as T;
}

export async function login(username: string, password: string): Promise<User> {
  const response = await fetch("/api/session/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, password }),
  });
  return readResponse<User>(response);
}

export async function logout(): Promise<void> {
  const response = await fetch("/api/session/logout", {
    method: "POST",
  });
  await readResponse<{ ok: boolean }>(response);
}

export async function postAction<TPayload extends object>(
  path: string,
  payload: TPayload,
): Promise<ActionResponse> {
  const response = await fetch(`/api/proxy${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return readResponse<ActionResponse>(response);
}

export async function postFormData(
  path: string,
  formData: FormData,
): Promise<ActionResponse> {
  const response = await fetch(`/api/proxy${path}`, {
    method: "POST",
    body: formData,
  });
  return readResponse<ActionResponse>(response);
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`/api/proxy${path}`, {
    method: "GET",
  });
  return readResponse<T>(response);
}

export async function postJson<TResponse, TPayload extends object>(
  path: string,
  payload: TPayload,
): Promise<TResponse> {
  const response = await fetch(`/api/proxy${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return readResponse<TResponse>(response);
}
