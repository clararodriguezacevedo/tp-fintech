// Every page shows the owner's real IOL portfolio, so the site requires logging in. Without a
// valid session cookie, requests go to /login (which then sends you back where you were going).
// Only enforced in production builds with SITE_PASSWORD set, so `npm run dev` stays open.
import { NextResponse, type NextRequest } from "next/server";

import { authEnabled, isValidSessionToken, SESSION_COOKIE } from "@/lib/session";

export async function middleware(req: NextRequest) {
  if (!authEnabled() || req.nextUrl.pathname === "/login") return NextResponse.next();

  const token = req.cookies.get(SESSION_COOKIE)?.value;
  if (await isValidSessionToken(token, process.env.SITE_PASSWORD!)) return NextResponse.next();

  const login = new URL("/login", req.url);
  if (req.nextUrl.pathname !== "/") login.searchParams.set("next", req.nextUrl.pathname);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
