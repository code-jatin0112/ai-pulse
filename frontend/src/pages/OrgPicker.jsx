import React, { useState } from "react";
import { api, setToken } from "../api.js";

export default function OrgPicker({ orgs, onPick }) {
  const [error, setError] = useState("");

  async function pick(o) {
    setError("");
    try {
      const data = await api("/auth/select-org", { method: "POST", body: JSON.stringify({ org_id: o.org_id }) });
      setToken(data.token);
      onPick(o);
    } catch (err) {
      setError(err.message || "Failed to select organization");
    }
  }

  return (
    <div className="card">
      <h2>Choose an organization</h2>
      {error && <p className="error">{error}</p>}
      {orgs.map((o) => (
        <p key={o.org_id}>
          <button onClick={() => pick(o)}>{o.org_name}</button> <small>({o.role})</small>
        </p>
      ))}
    </div>
  );
}
