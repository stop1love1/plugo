import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { login } from "../lib/api";
import { useStore } from "../lib/store";

export default function Login() {
  const navigate = useNavigate();
  const { user, setUser } = useStore();
  const [submitting, setSubmitting] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (user) {
      navigate("/", { replace: true });
    }
  }, [user, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) return;
    setSubmitting(true);

    try {
      const data = await login({ username, password });
      setUser({
        username: data.username,
        role: data.role,
        token: data.access_token,
      });
      toast.success("Welcome back!");
      navigate("/", { replace: true });
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail || "Authentication failed"
          : "Authentication failed";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 text-2xl font-bold text-primary-600 mb-2">
            <img src={new URL("../assets/images/logo.png", import.meta.url).href} alt="Plugo" className="w-10 h-10" />
            Plugo
          </div>
          <p className="text-gray-500">Sign in to your dashboard</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white p-6 rounded-xl border border-gray-200 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="plugo"
              autoFocus
              className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-primary-600 text-white py-2.5 rounded-lg hover:bg-primary-700 disabled:opacity-50 font-medium"
          >
            {submitting ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
