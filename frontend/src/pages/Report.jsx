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
      setSuccess("Your diagnostic answers and report have been deleted from the active AI Pulse database.");
      setConfirming(false);
      setReport({
        name: report?.name || "Employee",
        organization: report?.organization || "",
        answered: 0,
        average_score: null,
        level: "Not assessed",
        risks: [],
        next_steps: [],
        growth_insights: null,
      });
    } catch (err) {
      setError(err.message || "Failed to delete diagnostic data");
    } finally {
      setDeleting(false);
    }
  }

  if (error && !report) return <p className="error">{error}</p>;
  if (!report) return <p>Loading…</p>;

  if (report.answered === 0 || report.level === "Not assessed") {
    return (
      <div className="card">
        <h2>{report.name}</h2>
        <p>No diagnostic completed yet.</p>
        {error && <p className="error">{error}</p>}
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

      {report.growth_insights && (
        <div style={{ marginTop: "24px", paddingTop: "20px", borderTop: "1px solid #e4e7ec" }}>
          <h3 style={{ margin: "0 0 8px 0" }}>My AI Growth Insights</h3>
          <p style={{ color: "#475467", fontSize: "14px", margin: "0 0 16px 0" }}>
            Performance breakdown across key competency areas:
          </p>

          <div style={{ display: "grid", gap: "12px", marginBottom: "20px" }}>
            {report.growth_insights.breakdown.map((item) => (
              <div
                key={item.key}
                style={{
                  background: "#f8f9fc",
                  border: "1px solid #eaecf0",
                  padding: "12px 14px",
                  borderRadius: "8px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                  <span style={{ fontWeight: "600", fontSize: "14px" }}>{item.name}</span>
                  <span style={{ fontWeight: "bold", fontSize: "14px", color: "#3f2a71" }}>
                    {item.score.toFixed(1)} / 5.0
                  </span>
                </div>
                <div
                  style={{
                    background: "#eaecf0",
                    borderRadius: "4px",
                    height: "8px",
                    overflow: "hidden",
                    marginBottom: "6px",
                  }}
                  role="progressbar"
                  aria-valuenow={item.score}
                  aria-valuemin="1"
                  aria-valuemax="5"
                  aria-label={`${item.name} score`}
                >
                  <div
                    style={{
                      background: "#3f2a71",
                      height: "100%",
                      width: `${(item.score / 5) * 100}%`,
                      borderRadius: "4px",
                    }}
                  />
                </div>
                <p style={{ margin: 0, fontSize: "12px", color: "#475467" }}>{item.description}</p>
              </div>
            ))}
          </div>

          {report.growth_insights.strongest_area && (
            <div
              style={{
                background: "#edfcf2",
                border: "1px solid #a6f4c5",
                borderRadius: "8px",
                padding: "12px 14px",
                marginBottom: "12px",
              }}
            >
              <p style={{ margin: 0, color: "#027a48", fontWeight: "600", fontSize: "14px" }}>
                Key Strength: {report.growth_insights.strongest_area.name} ({report.growth_insights.strongest_area.score.toFixed(1)} / 5.0)
              </p>
            </div>
          )}

          {report.growth_insights.improvement_area && (
            <div
              style={{
                background: "#fef6ee",
                border: "1px solid #f9dbaf",
                borderRadius: "8px",
                padding: "12px 14px",
              }}
            >
              <p style={{ margin: "0 0 6px 0", color: "#b54708", fontWeight: "600", fontSize: "14px" }}>
                Priority Improvement Area: {report.growth_insights.improvement_area.name} ({report.growth_insights.improvement_area.score.toFixed(1)} / 5.0)
              </p>
              <p style={{ margin: 0, fontSize: "13px", color: "#7a271a" }}>
                <strong>Action Recommendation:</strong> {report.growth_insights.improvement_area.recommendation}
              </p>
            </div>
          )}
        </div>
      )}

      <hr style={{ margin: "24px 0", border: "0", borderTop: "1px solid #e4e7ec" }} />

      {error && <p className="error">{error}</p>}
      {success && <p style={{ color: "#027a48", fontWeight: "bold" }}>{success}</p>}

      {!confirming ? (
        <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
          {onRetake && (
            <button onClick={onRetake}>
              Retake diagnostic
            </button>
          )}
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
            Are you sure? This will delete all your answers, AI scores, and report from the active AI Pulse database.
          </p>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
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

