import { NextResponse } from "next/server";

import { getServerApiBaseUrl } from "../../../../lib/api";

function extractSessionCookie(setCookieHeader: string | null): string | null {
  if (!setCookieHeader) {
    return null;
  }
  const match = setCookieHeader.match(/hostel_session=([^;]+)/);
  return match ? match[1] : null;
}

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
  const sessionValue = extractSessionCookie(response.headers.get("set-cookie"));
  if (sessionValue) {
    nextResponse.cookies.set("hostel_session", sessionValue, {
      httpOnly: true,
      path: "/",
      sameSite: "lax",
    });
  }
  return nextResponse;
}
