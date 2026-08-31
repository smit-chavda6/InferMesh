import { useState } from "react";
import { Boxes, Loader2 } from "lucide-react";
import { Button, Card, Input } from "@/components/ui/primitives";
import { useLogin } from "@/api/queries";
import { ApiError } from "@/api/client";

export function LoginPage() {
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const err =
    login.error instanceof ApiError
      ? login.error.message
      : login.error
        ? "Login failed."
        : null;

  return (
    <div className="grid min-h-full place-items-center bg-bg p-4">
      <Card className="w-full max-w-sm p-6">
        <div className="mb-5 flex items-center gap-2.5">
          <div className="grid size-9 place-items-center rounded-md bg-accent text-accent-fg">
            <Boxes className="size-5" />
          </div>
          <div>
            <div className="text-sm font-semibold">LLM Gateway</div>
            <div className="text-xs text-text-muted">Observability dashboard</div>
          </div>
        </div>

        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            login.mutate({ email, password });
          }}
        >
          <div className="space-y-1">
            <label className="text-xs font-medium text-text-muted" htmlFor="email">
              Admin email
            </label>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-text-muted" htmlFor="password">
              Password
            </label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {err && <div className="rounded-md bg-err-bg px-3 py-2 text-xs text-err">{err}</div>}

          <Button type="submit" className="w-full" disabled={login.isPending}>
            {login.isPending && <Loader2 className="size-4 animate-spin" />}
            Sign in
          </Button>
        </form>
      </Card>
    </div>
  );
}
