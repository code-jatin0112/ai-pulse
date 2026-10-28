import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Diagnostic({ onDone }) {
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/diagnostic/questions")
      .then(setQuestions)
      .catch((err) => setError(err.message));
  }, []);

  async function submit() {
    setError("");
    setSubmitting(true);
    try {
      const payload = Object.entries(answers).map(([question_id, answer]) => ({ question_id, answer }));
      await api("/diagnostic/submit", { method: "POST", body: JSON.stringify({ answers: payload }) });
      onDone();
    } catch (err) {
      setError(err.message || "Failed to submit diagnostic");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="card">
      <h2>Your AI diagnostic</h2>
      {error && <p className="error">{error}</p>}
      {questions.map((q) => (
        <div key={q.id}>
          <p><b>{q.text}</b></p>
          {q.type === "mcq" ? (
            <select onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} defaultValue="">
              <option value="" disabled>Choose…</option>
              {q.options.map((o) => <option key={o}>{o}</option>)}
            </select>
          ) : (
            <textarea rows={4} onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} />
          )}
        </div>
      ))}
      <button onClick={submit} disabled={submitting} style={{ marginTop: "16px" }}>
        {submitting ? "Submitting…" : "Submit"}
      </button>
    </div>
  );
}
