import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../lib/api";

export function Login() {
  const nav = useNavigate();
  const [email, setEmail] = useState("admin@local");
  const [password, setPassword] = useState("admin");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const { access_token } = await api.login(email, password);
      setToken(access_token);
      nav("/", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="terminal-shell" style={{ maxWidth: 420, paddingTop: 80 }}>
      <h1 className="glow" style={{ fontSize: 22, letterSpacing: "0.2em" }}>AUREUS</h1>
      <p className="label" style={{ marginBottom: 24 }}>Gold Trading Terminal · Paper Default</p>
      <div className="panel">
        <h2 className="panel-title">Operator Login</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <span className="label">Email</span>
            <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <span className="label">Password</span>
            <input className="input" type="password" value={password}
                   onChange={(e) => setPassword(e.target.value)}
                   onKeyDown={(e) => e.key === "Enter" && submit()} />
          </div>
          {error && <span className="warn">⚠ {error}</span>}
          <button className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? "Authenticating…" : "Login"}
          </button>
          <span className="label">default: admin@local / admin</span>
        </div>
      </div>
    </div>
  );
}
