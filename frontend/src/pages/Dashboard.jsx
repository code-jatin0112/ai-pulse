import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Dashboard({ org }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api(`/dashboard?org_id=${org.org_id}`)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [org]);

  if (error) {
    return (
      <div className="card">
        <h2>Dashboard</h2>
        <p className="error">{error}</p>
      </div>
    );
  }

  if (!data) return <p>Loading…</p>;

  return (
    <div className="card">
      <h2>{data.organization} Dashboard</h2>
      <p style={{ color: "#667085", fontSize: "0.9rem" }}>
        Results are shown only for teams with at least 5 completed diagnostics.
      </p>

      {data.departments.length === 0 ? (
        <p>No department has reached the minimum threshold of 5 completed diagnostics yet.</p>
      ) : (
        <div>
          <h3>Departments</h3>
          <ul>
            {data.departments.map((d) => (
              <li key={d.department}>
                <b>{d.department}</b>: {d.level} (avg score: {d.average_score}, completers: {d.responded}/{d.employees})
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h3>Top Risks</h3>
        {data.top_risks && data.top_risks.length > 0 ? (
          <ul>
            {data.top_risks.map(([risk, count]) => (
              <li key={risk}>
                {risk}: {count}
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ color: "#667085" }}>No aggregate risks flagged for qualified departments.</p>
        )}
      </div>
    </div>
  );
}

