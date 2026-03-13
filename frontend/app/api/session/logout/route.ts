import { NextResponse } from "next/server";

import { getServerApiBaseUrl } from "../../../../lib/api";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  await fetch(`${getServerApiBaseUrl()}/auth/logout`, {
    method: "POST",
    headers: {
      Cookie: cookieHeader,
    },
    cache: "no-store",
  }).catch(() => null);
  const response = NextResponse.json({ ok: true });
  response.cookies.set("hostel_session", "", {
    httpOnly: true,
    path: "/",
    sameSite: "lax",
    expires: new Date(0),
  });
  return response;
}
