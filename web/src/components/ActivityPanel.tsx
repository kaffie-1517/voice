import { useEffect, useState } from "react";
import { api } from "../api";
import type { Activity } from "../types";

/** What Relay actually did, and how much it has learned. */
export function ActivityPanel() {
  const [data, setData] = useState<Activity | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => api.activity().then((d) => alive && setData(d)).catch(() => undefined);
    load();
    const id = setInterval(load, 4000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <div className="stage">
      <section className="panel">
        <h2>What Relay has learned</h2>
        <p style={{ color: "var(--muted)", marginTop: 0 }}>
          Every sentence you choose is remembered and shapes the next suggestions.
          {data && (
            <> So far: <b style={{ color: "var(--text)" }}>{data.memory.recorded}</b> choices, stored in <code>{data.memory.backend}</code>.</>
          )}
        </p>

        <h2 style={{ marginTop: 20 }}>Things done for you</h2>
        <div className="activity">
          {(data?.entries ?? []).map((e, i) => (
            <div key={i} className="row">
              <span className="kind">{e.kind}</span>
              <span>{e.detail}</span>
            </div>
          ))}
          {data && data.entries.length === 0 && (
            <div className="suggestions-empty">Nothing yet. Ask for a reminder, or to send something, and it will show here.</div>
          )}
        </div>
      </section>
    </div>
  );
}
