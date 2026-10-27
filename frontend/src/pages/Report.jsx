import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Report({ onRetake }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    api("/reports/me")
      .then(setReport)
      .catch((err) => setError(err.message));
  }, []);

  async function handleDelete() {
    setError("");
    setDeleting(true);
    try {
      await api("/diagnostic/me", { method: "DELETE" });
      setSuccess("Your diagnostic answers and report have been permanently deleted.");
      setConfirming(false);
      setReport({
        name: report?.name || "Employee",
        organization: report?.organization || "",
        answered: 0,
        average_score: null,
        level: "Not assessed",
        risks: [],
        next_steps: [],
      });
    } catch (err) {
      setError(err.message || "Failed to delete diagnostic data");
    } finally {
      setDeleting(false);
    }
  }

  if (error && !report) return <p className="error">{error}</p>;
  if (!report) return <p>Loading…</p>;

  if (report.answered === 0) {
    return (
      <div className="card">
        <h2>{report.name}</h2>
        <p>No diagnostic completed yet.</p>
        {success && <p style={{ color: "#027a48", fontWeight: "bold" }}>{success}</p>}
        {onRetake && (
          <button style={{ marginTop: "12px" }} onClick={onRetake}>
            Take diagnostic
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="card">
      <h2>{report.name}: {report.level}</h2>
      <p>Average score: {report.average_score}</p>
      <h3>Risks</h3>
      {report.risks.length === 0 ? (
        <p>No risks flagged.</p>
      ) : (
        <ul>
          {report.risks.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      <h3>Next steps</h3>
      <ul>
        {report.next_steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>

      <hr style={{ margin: "24px 0", border: "0", borderTop: "1px solid #e4e7ec" }} />

      {error && <p className="error">{error}</p>}
      {success && <p style={{ color: "#027a48", fontWeight: "bold" }}>{success}</p>}

      {!confirming ? (
        <div>
          <button
            style={{ background: "#d92d20" }}
            onClick={() => setConfirming(true)}
          >
            Delete my diagnostic data
          </button>
        </div>
      ) : (
        <div style={{ background: "#fef3f2", padding: "16px", borderRadius: "8px", border: "1px solid #fee4e2" }}>
          <p style={{ color: "#b42318", margin: "0 0 12px 0", fontWeight: "bold" }}>
            Are you sure? This will permanently delete all your answers, AI scores, and report from AI Pulse.
          </p>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              style={{ background: "#d92d20" }}
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? "Deleting…" : "Yes, permanently delete"}
            </button>
            <button
              style={{ background: "#667085" }}
              onClick={() => setConfirming(false)}
              disabled={deleting}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

