import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { useAuth } from "../lib/auth";

export function LoginPage() {
  const { token, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (token) {
    return <Navigate to="/" replace />;
  }

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(email, password);
      navigate("/");
    } catch {
      setError("Invalid email or password");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mx-auto mt-24 w-full max-w-md rounded-lg border bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Sign in to Labo</h1>
      <form onSubmit={onSubmit} className="mt-4 space-y-3">
        <input
          className="w-full rounded border px-3 py-2"
          placeholder="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          className="w-full rounded border px-3 py-2"
          placeholder="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          disabled={isSubmitting}
          className="w-full rounded bg-slate-900 px-3 py-2 text-white disabled:opacity-50"
        >
          {isSubmitting ? "Signing in..." : "Sign in"}
        </button>
      </form>
      <p className="mt-4 text-sm text-slate-600">
        No account?{" "}
        <Link to="/register" className="text-slate-900 underline">
          Register
        </Link>
      </p>
    </div>
  );
}
