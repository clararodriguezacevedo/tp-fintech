// Password-protects the whole site with HTTP Basic Auth: the pages show the owner's real IOL
// portfolio, so they can't be public. The browser asks once and remembers it. Any user name
// works; the password is SITE_PASSWORD. Only enforced in production builds, so `npm run dev` stays open.
import { NextResponse, type NextRequest } from "next/server";

function safeEqual(a: string, b: string) {
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0;
}

export function middleware(req: NextRequest) {
  const password = process.env.SITE_PASSWORD;
  if (!password || process.env.NODE_ENV !== "production") return NextResponse.next();

  const header = req.headers.get("authorization");
  if (header?.startsWith("Basic ")) {
    try {
      const decoded = atob(header.slice(6));
      const given = decoded.slice(decoded.indexOf(":") + 1);
      if (safeEqual(given, password)) return NextResponse.next();
    } catch {
      // malformed header: fall through to the challenge
    }
  }
  return new NextResponse("Acceso restringido.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="El Parque", charset="UTF-8"' },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
