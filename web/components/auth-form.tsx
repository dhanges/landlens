"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { useAuth, useMe } from "@/lib/queries";

/** Only same-site paths are followed after sign-in (no open redirect). */
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/map";
  return raw;
}

export function AuthForm({ kind }: { kind: "login" | "signup" }) {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const auth = useAuth(kind);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const signup = kind === "signup";
  const me = useMe();

  const err = auth.error instanceof ApiError ? auth.error : null;
  const fieldErr = (f: string) =>
    err?.code === "validation_error" &&
    Array.isArray(err.details) &&
    (err.details as { loc?: string[] }[]).some((d) => d.loc?.includes(f));
  const message =
    err?.code === "validation_error"
      ? fieldErr("password")
        ? "Use a password of at least 10 characters."
        : "Enter a valid email address."
      : err?.code === "rate_limited"
        ? `Too many attempts. Wait ${err.retryAfter ?? 60} seconds and try again.`
        : err?.message;

  if (me.data && !auth.isPending && !auth.isSuccess) {
    return (
      <div className="card mx-auto w-full max-w-[420px] p-8">
        <h1 className="mb-1 text-[32px] leading-tight tracking-display">You are signed in</h1>
        <p className="mb-6 text-muted">
          Signed in as {me.data.email}, with <span className="num">{me.data.credit_balance}</span> credits.
        </p>
        <Button asChild variant="primary" size="block">
          <Link href={next}>Continue</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="card mx-auto w-full max-w-[420px] p-8">
      <h1 className="mb-1 text-[32px] leading-tight tracking-display">{signup ? "Create your account" : "Sign in"}</h1>
      <p className="mb-6 text-muted">
        {signup
          ? "Free to research. You get 3 report credits when you sign up."
          : "Welcome back. Your credits and unlocked reports are waiting."}
      </p>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          auth.mutate({ email, password }, { onSuccess: () => router.push(next) });
        }}
      >
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={fieldErr("email") || undefined}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete={signup ? "new-password" : "current-password"}
            required
            minLength={signup ? 10 : 1}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={fieldErr("password") || undefined}
          />
          {signup && <span className="text-[12px] text-muted">At least 10 characters.</span>}
        </div>
        {message && (
          <p role="alert" className="text-[14px] text-down">
            {message}
          </p>
        )}
        <Button type="submit" variant="primary" size="block" disabled={auth.isPending}>
          {auth.isPending ? (signup ? "Creating account…" : "Signing in…") : signup ? "Create account" : "Sign in"}
        </Button>
      </form>
      <p className="mt-5 text-[14px] text-muted">
        {signup ? "Already have an account? " : "New to LandLens? "}
        <Link href={`/${signup ? "login" : "signup"}?next=${encodeURIComponent(next)}`}>
          {signup ? "Sign in" : "Create an account"}
        </Link>
      </p>
    </div>
  );
}
