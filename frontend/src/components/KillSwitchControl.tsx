import { useState } from "react";
import { api } from "../lib/api";

// Engaging the kill switch is a single confirm so halting stays fast.
export function KillSwitchControl({
  active, onChanged,
}: {
  active: boolean;
  onChanged: () => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const engage = async () => {
    setBusy(true);
    try {
      await api.setKillSwitch(true, "manual halt from command center");
      setConfirmOpen(false);
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const release = async () => {
    setBusy(true);
    try {
      await api.setKillSwitch(false, "release from command center");
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="row" style={{ marginBottom: 10 }}>
        <span className="label">Kill Switch</span>
        <span className={`badge ${active ? "badge-on" : ""}`}>
          {active ? "HALTED" : "ARMED · READY"}
        </span>
      </div>

      {active ? (
        <button className="btn" style={{ width: "100%" }} disabled={busy} onClick={release}>
          {busy ? "Releasing…" : "Release Halt"}
        </button>
      ) : (
        <button className="btn btn-danger" style={{ width: "100%" }}
                onClick={() => setConfirmOpen(true)}>
          Engage Kill Switch
        </button>
      )}

      {confirmOpen && (
        <div className="modal-overlay" onClick={() => setConfirmOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">Engage Kill Switch</div>
            <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <p className="warn">
                This immediately blocks <span className="up">all order placement</span> and
                halts signal emission. One click to halt.
              </p>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                <button className="btn" onClick={() => setConfirmOpen(false)} disabled={busy}>
                  Cancel
                </button>
                <button className="btn btn-danger" onClick={engage} disabled={busy}>
                  {busy ? "Halting…" : "Halt Now"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
