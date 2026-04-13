import { NextResponse } from "next/server";

import { getServerApiBaseUrl } from "../../../../lib/api";
import { forwardSessionCookie } from "../../../../lib/session-cookie";

export async function POST(request: Request) {
  const payload = await request.json();
  const response = await fetch(`${getServerApiBaseUrl()}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const body = await response.text();
  const nextResponse = new NextResponse(body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") ?? "application/json",
    },
  });
  forwardSessionCookie(response, nextResponse);
  return nextResponse;
}
