import Link from "next/link";

export default function NotFound() {
  return (
    <main className="grid min-h-screen place-items-center bg-[#070b13] px-6 text-center text-ink">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-signal">404</p>
        <h1 className="mt-3 text-3xl font-black">Page not found</h1>
        <p className="mt-3 text-muted">That SaudiBuild page does not exist.</p>
        <Link href="/" className="mt-6 inline-flex rounded-md bg-signal px-4 py-2 font-bold text-slate-950">Return home</Link>
      </div>
    </main>
  );
}
