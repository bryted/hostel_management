import { NextResponse } from "next/server";

import { getServerApiBaseUrl } from "../../../../lib/api";

function decodedCookieHeader(request: Request): string {
  const cookieHeader = request.headers.get("cookie") ?? "";
  return cookieHeader.replace(
    /hostel_session=([^;]+)/,
    (_match, value: string) => `hostel_session=${decodeURIComponent(value)}`,
  );
}

export async function POST(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const body = await request.arrayBuffer();
  const response = await fetch(`${getServerApiBaseUrl()}/${path.join("/")}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      Cookie: decodedCookieHeader(request),
      ...(request.headers.get("content-type")
        ? { "Content-Type": request.headers.get("content-type") as string }
        : {}),
    },
    body,
    cache: "no-store",
  });
  const payload = await response.text();
  return new NextResponse(payload, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") ?? "application/json",
    },
  });
}

export async function GET(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const url = new URL(request.url);
  const search = url.searchParams.toString();
  const response = await fetch(
    `${getServerApiBaseUrl()}/${path.join("/")}${search ? `?${search}` : ""}`,
    {
      method: "GET",
      headers: {
        Accept: request.headers.get("accept") ?? "*/*",
        Cookie: decodedCookieHeader(request),
      },
      cache: "no-store",
    },
  );
  const payload = await response.arrayBuffer();
  const nextResponse = new NextResponse(payload, {
    status: response.status,
  });
  const contentType = response.headers.get("content-type");
  const disposition = response.headers.get("content-disposition");
  if (contentType) {
    nextResponse.headers.set("Content-Type", contentType);
  }
  if (disposition) {
    nextResponse.headers.set("Content-Disposition", disposition);
  }
  return nextResponse;
}
