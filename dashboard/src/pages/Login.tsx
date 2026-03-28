import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { login, getSetupStatus } from "../lib/api";
import { useStore } from "../lib/store";
import { MessageSquare, Terminal } from "lucide-react";

export default function Login() {
  const navigate = useNavigate();
  const { user, setUser } = useStore();
  const [needsSetup, setNeedsSetup] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (user) {
      navigate("/", { replace: true });
      return;
    }
    getSetupStatus()
      .then((data) => {
        setNeedsSetup(!data.has_users);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
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
    } catch (err: any) {
      const msg = err.response?.data?.detail || "Authentication failed";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 text-2xl font-bold text-primary-600 mb-2">
            <img src="/src/assets/images/logo.png" alt="Plugo" className="w-10 h-10" />
            Plugo
          </div>
          <p className="text-gray-500">Sign in to your dashboard</p>
        </div>

        {needsSetup ? (
          <div className="bg-white p-6 rounded-xl border border-gray-200 space-y-4">
            <div className="flex items-center gap-2 text-amber-600">
              <Terminal className="w-5 h-5" />
              <h3 className="font-semibold">Setup Required</h3>
            </div>
            <p className="text-sm text-gray-600">
              No admin account found. Create one using the CLI:
            </p>
            <div className="bg-gray-900 text-green-400 p-3 rounded-lg font-mono text-sm">
              <p>cd backend</p>
              <p>python manage.py create-admin</p>
            </div>
            <p className="text-xs text-gray-400">
              You can also pass flags: <code className="text-gray-500">-u username -p password</code>
            </p>
            <button
              onClick={() => {
                setNeedsSetup(false);
                setLoading(true);
                getSetupStatus()
                  .then((data) => {
                    setNeedsSetup(!data.has_users);
                    setLoading(false);
                  })
                  .catch(() => setLoading(false));
              }}
              className="w-full text-sm text-primary-600 hover:text-primary-700 py-2"
            >
              I've created an account — refresh
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="bg-white p-6 rounded-xl border border-gray-200 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin"
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
            <p className="text-center text-xs text-gray-400">
              Forgot password? Run: <code className="text-gray-500">python manage.py reset-password</code>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
