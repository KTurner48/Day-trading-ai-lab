import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

const SYMBOLS = ["XAU_USD", "GC", "GLD"];

// Polls the simulated quote endpoint and shows direction by luminance.
export function LiveQuotes() {
  const [prices, setPrices] = useState<Record<string, { price: number; prev: number }>>({});
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const tick = async () => {
      for (const sym of SYMBOLS) {
        try {
          const q = await api.quote(sym);
          setPrices((prev) => ({
            ...prev,
            [sym]: { price: Number(q.price), prev: prev[sym]?.price ?? Number(q.price) },
          }));
        } catch {
          /* ignore transient errors */
        }
      }
    };
    void tick();
    timer.current = setInterval(tick, 4000);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, []);

  return (
    <div style={{ display: "flex", gap: 1, border: "1px solid var(--term-edge)" }}>
      {SYMBOLS.map((sym) => {
        const p = prices[sym];
        const dir = p ? Math.sign(p.price - p.prev) : 0;
        return (
          <div key={sym} style={{ flex: 1, padding: "10px 14px", background: "var(--term-panel)" }}>
            <div className="label">{sym.replace("_", "/")}</div>
            <div className={`mono-price ${dir > 0 ? "up" : dir < 0 ? "down" : ""}`}>
              {p ? p.price.toFixed(2) : "––––.––"}
              {dir !== 0 && <span style={{ fontSize: 10, marginLeft: 4 }}>{dir > 0 ? "▲" : "▼"}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
