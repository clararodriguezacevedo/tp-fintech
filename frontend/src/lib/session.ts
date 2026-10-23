// Signed login session: the cookie holds an expiry time plus an HMAC of it keyed with
// SITE_PASSWORD, so it can't be forged, and changing the password logs everyone out.
// Uses Web Crypto, which works both in the middleware (edge) and in server actions (Node).

export const SESSION_COOKIE = "parque_session";
export const SESSION_DAYS = 30;

const encoder = new TextEncoder();

function toBase64Url(bytes: ArrayBuffer) {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function sign(value: string, secret: string) {
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return toBase64Url(await crypto.subtle.sign("HMAC", key, encoder.encode(value)));
}

/** Constant-time string comparison. */
export function safeEqual(a: string, b: string) {
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0;
}

export async function createSessionToken(secret: string) {
  const expires = String(Date.now() + SESSION_DAYS * 24 * 60 * 60 * 1000);
  return `${expires}.${await sign(expires, secret)}`;
}

export async function isValidSessionToken(token: string | undefined, secret: string) {
  if (!token) return false;
  const [expires, signature] = token.split(".");
  if (!expires || !signature || Number(expires) < Date.now()) return false;
  return safeEqual(signature, await sign(expires, secret));
}

/** Login is only enforced in production builds with a password configured. */
export function authEnabled() {
  return Boolean(process.env.SITE_PASSWORD) && process.env.NODE_ENV === "production";
}
