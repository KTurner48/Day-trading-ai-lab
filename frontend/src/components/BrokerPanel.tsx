import type { CommandCenter } from "../lib/api";

export function BrokerPanel({ brokers }: { brokers: CommandCenter["brokers"] }) {
  return (
    <div className="panel">
      <h2 className="panel-title">Broker Connections</h2>
      {brokers.length === 0 ? (
        <div className="label">No broker connections</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {brokers.map((b) => (
            <div key={b.name} className="row"
                 style={{ borderBottom: "1px solid var(--term-line)", paddingBottom: 8 }}>
              <div>
                <div style={{ color: "var(--term-silver)" }}>{b.name}</div>
                <div className="label">{b.broker_type}</div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span className={`badge ${b.order_capable ? "badge-on" : ""}`}>
                  {b.order_capable ? "ORDER-CAPABLE" : "STATUS-ONLY"}
                </span>
                <span className="label">{b.status}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="label" style={{ marginTop: 10 }}>
        Only the paper broker can place orders. Live adapters are status-only; live ordering is disabled.
      </p>
    </div>
  );
}
