import { LoginForm } from "./login-form";

export const metadata = { title: "Entrar | El Parqué" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-8 text-center text-2xl font-semibold tracking-tight">El Parqué</h1>
        <div className="rounded-xl border border-border p-6">
          <LoginForm next={next ?? "/"} />
        </div>
      </div>
    </main>
  );
}
