import { NextResponse } from "next/server";

import { getServerApiBaseUrl } from "../../../../lib/api";
import { forwardSessionCookie, isSecureRequest } from "../../../../lib/session-cookie";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const upstreamResponse = await fetch(`${getServerApiBaseUrl()}/auth/logout`, {
    method: "POST",
    headers: {
      Cookie: cookieHeader,
    },
    cache: "no-store",
  }).catch(() => null);
  const response = NextResponse.json({ ok: true });
  if (!upstreamResponse || !forwardSessionCookie(upstreamResponse, response)) {
    response.cookies.set("hostel_session", "", {
      httpOnly: true,
      path: "/",
      sameSite: "lax",
      secure: isSecureRequest(request),
      expires: new Date(0),
    });
  }
  return response;
}
