import type { NextResponse } from "next/server";

export function forwardSessionCookie(upstream: Response, downstream: NextResponse): boolean {
  const setCookieHeader = upstream.headers.get("set-cookie");
  if (!setCookieHeader) {
    return false;
  }
  downstream.headers.append("set-cookie", setCookieHeader);
  return true;
}

export function isSecureRequest(request: Request): boolean {
  const forwardedProto = request.headers.get("x-forwarded-proto");
  if (forwardedProto) {
    return forwardedProto.split(",")[0].trim() === "https";
  }
  return new URL(request.url).protocol === "https:";
}
