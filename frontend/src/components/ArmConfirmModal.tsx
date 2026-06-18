import { useEffect, useState } from "react";
import { ARM_PHRASE, isArmPhraseValid } from "../lib/confirm";

// Typed-confirmation gate for leaving paper mode.
export function ArmConfirmModal({
  open, targetLabel, onConfirm, onClose, busy,
}: {
  open: boolean;
  targetLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  busy?: boolean;
}) {
  const [text, setText] = useState("");
  useEffect(() => { if (!open) setText(""); }, [open]);
  if (!open) return null;
  const valid = isArmPhraseValid(text);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">Confirm Live-Adjacent Mode</div>
        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <p className="warn">
            Switching to <span className="up">{targetLabel}</span> leaves the safe paper
            default. Live order placement stays disabled, but signal/execution routing
            changes now. Type <span className="up">{ARM_PHRASE}</span> to proceed.
          </p>
          <div>
            <span className="label">Type "{ARM_PHRASE}" to confirm</span>
            <input className="input" aria-label="arm-phrase" autoFocus value={text}
                   onChange={(e) => setText(e.target.value)} placeholder={ARM_PHRASE} />
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
            <button className="btn btn-primary" disabled={!valid || busy} onClick={onConfirm}>
              {busy ? "Arming…" : "Confirm"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
