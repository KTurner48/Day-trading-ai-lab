import { useState } from "react";
import { api } from "../lib/api";
import { requiresArmConfirmation } from "../lib/confirm";
import { ArmConfirmModal } from "./ArmConfirmModal";

const MODES = [
  { id: "paper", label: "PAPER" },
  { id: "live_manual_approval", label: "LIVE · MANUAL" },
  { id: "live_auto", label: "LIVE · AUTO" },
];

export function TradingModeControl({
  current, onChanged,
}: {
  current: string;
  onChanged: () => void;
}) {
  const [pending, setPending] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = async (mode: string) => {
    setBusy(true);
    setError(null);
    try {
      await api.setMode(mode);
      setPending(null);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  };

  const request = (mode: string) => {
    if (mode === current) return;
    setError(null);
    if (requiresArmConfirmation(mode)) setPending(mode);
    else void apply(mode);
  };

  const targetLabel = MODES.find((m) => m.id === pending)?.label ?? "";

  return (
    <div>
      <div className="row" style={{ marginBottom: 10 }}>
        <span className="label">Trading Mode</span>
        <span className={`badge ${current !== "paper" ? "badge-on" : ""}`}>
          {MODES.find((m) => m.id === current)?.label ?? current}
        </span>
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        {MODES.map((m) => (
          <button key={m.id} className={`btn ${m.id === current ? "btn-primary" : ""}`}
                  style={{ flex: 1, padding: "10px 6px" }} disabled={busy}
                  onClick={() => request(m.id)}>
            {m.label}
          </button>
        ))}
      </div>
      {error && <p className="warn" style={{ marginTop: 8 }}>⚠ {error}</p>}
      <ArmConfirmModal open={pending !== null} targetLabel={targetLabel} busy={busy}
                       onClose={() => setPending(null)}
                       onConfirm={() => pending && apply(pending)} />
    </div>
  );
}
