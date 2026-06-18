import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, clearToken, type CommandCenter } from "../lib/api";
import { TradingModeControl } from "../components/TradingModeControl";
import { KillSwitchControl } from "../components/KillSwitchControl";
import { LiveQuotes } from "../components/LiveQuotes";
import { BrokerPanel } from "../components/BrokerPanel";

export function Dashboard() {
  const nav = useNavigate();
  const [data, setData] = useState<CommandCenter | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api.commandCenter());
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load";
      setError(msg);
      if (msg.toLowerCase().includes("token") || msg.includes("401")) {
        clearToken();
        nav("/login", { replace: true });
      }
    }
  }, [nav]);

  useEffect(() => { void load(); }, [load]);

  const generate = async () => {
    setBusy(true);
    try { await api.generate("XAU_USD"); await load(); }
    finally { setBusy(false); }
  };

  const logout = () => { clearToken(); nav("/login", { replace: true }); };

  if (error && !data) {
    return <div className="terminal-shell"><p className="warn">⚠ {error}</p>
      <button className="btn" onClick={logout}>Back to login</button></div>;
  }
  if (!data) return <div className="terminal-shell"><p className="label">Loading command center…</p></div>;

  const s = data.settings;
  return (
    <div className="terminal-shell">
      <div className="row" style={{ marginBottom: 20 }}>
        <div>
          <h1 className="glow" style={{ fontSize: 20, letterSpacing: "0.2em", margin: 0 }}>
            COMMAND CENTER
          </h1>
          <span className="label">AUREUS · single-operator</span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className={`badge ${s.trading_mode !== "paper" ? "badge-on" : ""}`}>
            {s.trading_mode}
          </span>
          <span className={`badge ${s.kill_switch_active ? "badge-on" : ""}`}>
            {s.kill_switch_active ? "HALTED" : "NOMINAL"}
          </span>
          <button className="btn" onClick={logout}>Logout</button>
        </div>
      </div>

      <div style={{ marginBottom: 16 }}><LiveQuotes /></div>

      <div className="grid grid-3" style={{ marginBottom: 16 }}>
        <div className="panel">
          <span className="label">Balance</span>
          <div className="mono-price">
            {data.account ? `$${Number(data.account.balance).toLocaleString()}` : "—"}
          </div>
        </div>
        <div className="panel">
          <span className="label">Open Positions</span>
          <div className="mono-price">{data.open_positions.length}</div>
        </div>
        <div className="panel">
          <span className="label">Pending Signals</span>
          <div className="mono-price">{data.pending_count}</div>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 16 }}>
        <div className="panel">
          <h2 className="panel-title">Safety Controls</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <TradingModeControl current={s.trading_mode} onChanged={load} />
            <div style={{ height: 1, background: "var(--term-line)" }} />
            <KillSwitchControl active={s.kill_switch_active} onChanged={load} />
          </div>
        </div>
        <BrokerPanel brokers={data.brokers} />
      </div>

      <div className="panel">
        <div className="row" style={{ marginBottom: 12 }}>
          <h2 className="panel-title" style={{ margin: 0, border: "none" }}>Latest Signal</h2>
          <button className="btn btn-primary" onClick={generate} disabled={busy}>
            {busy ? "Generating…" : "Generate (Paper)"}
          </button>
        </div>
        {data.latest_signal ? (
          <div>
            <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
              <span className="badge badge-on">{data.latest_signal.action.toUpperCase()}</span>
              <span className="badge">{data.latest_signal.status}</span>
              <span className="badge">score {data.latest_signal.score}</span>
            </div>
            {data.latest_signal.reasoning && (
              <p className="warn">{data.latest_signal.reasoning}</p>
            )}
            {data.latest_signal.veto_reason && (
              <p className="warn">VETOED: {data.latest_signal.veto_reason}</p>
            )}
          </div>
        ) : (
          <div className="label">No signals yet — click Generate</div>
        )}
      </div>
    </div>
  );
}
