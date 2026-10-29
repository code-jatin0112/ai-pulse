import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Diagnostic({
  onDone,
  draftAnswers = {},
  onAnswerChange,
  onSubmissionSuccess,
}) {
  const [questions, setQuestions] = useState([]);
  const [localAnswers, setLocalAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  // If draftAnswers is provided by parent (App), use it; otherwise use local state
  const answers = onAnswerChange ? draftAnswers : localAnswers;

  function updateAnswer(qid, val) {
    if (onAnswerChange) {
      onAnswerChange(qid, val);
    } else {
      setLocalAnswers((prev) => ({ ...prev, [qid]: val }));
    }
  }

  useEffect(() => {
    api("/diagnostic/questions")
      .then((qs) => {
        setQuestions(qs);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  async function submit() {
    setError("");
    setSubmitting(true);
    try {
      const payload = Object.entries(answers).map(([question_id, answer]) => ({ question_id, answer }));
      await api("/diagnostic/submit", { method: "POST", body: JSON.stringify({ answers: payload }) });
      if (onSubmissionSuccess) {
        onSubmissionSuccess();
      }
      onDone();
    } catch (err) {
      setError(err.message || "Failed to submit diagnostic");
      // All answers remain intact in answers/draftAnswers for easy correction
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="card">
        <h2>Your AI diagnostic</h2>
        <p>Loading questions…</p>
      </div>
    );
  }

  if (questions.length === 0 && !error) {
    return (
      <div className="card">
        <h2>Your AI diagnostic</h2>
        <p>No questions available for your role at this time.</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>Your AI diagnostic</h2>
      {error && <p className="error">{error}</p>}
      {questions.map((q) => (
        <div key={q.id}>
          <p><b>{q.text}</b></p>
          {q.type === "mcq" ? (
            <select
              value={answers[q.id] || ""}
              onChange={(e) => updateAnswer(q.id, e.target.value)}
            >
              <option value="" disabled>Choose…</option>
              {q.options.map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
          ) : (
            <textarea
              rows={4}
              value={answers[q.id] || ""}
              onChange={(e) => updateAnswer(q.id, e.target.value)}
            />
          )}
        </div>
      ))}
      <button onClick={submit} disabled={submitting} style={{ marginTop: "16px" }}>
        {submitting ? "Submitting…" : "Submit"}
      </button>
    </div>
  );
}
