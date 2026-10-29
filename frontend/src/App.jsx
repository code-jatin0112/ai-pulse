import React, { useState } from "react";
import Login from "./pages/Login.jsx";
import OrgPicker from "./pages/OrgPicker.jsx";
import Diagnostic from "./pages/Diagnostic.jsx";
import Report from "./pages/Report.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import { setToken, clearToken } from "./api.js";

export default function App() {
  const [step, setStep] = useState("login");
  const [session, setSession] = useState(null);
  const [org, setOrg] = useState(null);
  const [history, setHistory] = useState([]);
  const [draftAnswers, setDraftAnswers] = useState({});

  function handleLoginSuccess(s) {
    setSession(s);
    setOrg(null);
    setHistory([]);
    setStep("org");
  }

  function handleSelectOrg(o) {
    if (!org || org.org_id !== o.org_id) {
      setDraftAnswers({});
    }
    setOrg(o);
    setHistory(["org"]);
    setStep(o.role === "admin" ? "dashboard" : "diagnostic");
  }

  function handleChangeOrg() {
    setOrg(null);
    // Explicitly clear draft answers so Organization A's drafts never populate Organization B
    setDraftAnswers({});
    // Restore base user-level token so selecting another org requires obtaining a fresh org-scoped JWT
    if (session?.token) {
      setToken(session.token);
    }
    setHistory((prev) => [...prev, step]);
    setStep("org");
  }

  function handleBack() {
    if (history.length > 0) {
      const prevStep = history[history.length - 1];
      setHistory((h) => h.slice(0, -1));
      // Guard: Back navigation must never bypass authentication into unauthenticated state
      if (prevStep === "login") {
        handleLogout();
        return;
      }
      if (prevStep === "org") {
        setOrg(null);
        // Leaving an organization back to the picker clears draft answers
        setDraftAnswers({});
        if (session?.token) {
          setToken(session.token);
        }
      }
      setStep(prevStep);
    } else {
      // Fallback to org selection
      setOrg(null);
      setDraftAnswers({});
      if (session?.token) {
        setToken(session.token);
      }
      setStep("org");
    }
  }

  function handleLogout() {
    clearToken();
    setSession(null);
    setOrg(null);
    setHistory([]);
    setDraftAnswers({});
    setStep("login");
  }

  const canGoBack = step !== "login" && step !== "org";

  return (
    <div className="wrap">
      <header className="nav-header">
        <div>
          <h1 style={{ margin: 0, fontSize: "28px" }}>AI Pulse</h1>
          {session && (
            <div style={{ fontSize: "14px", color: "#475467", marginTop: "4px" }}>
              <span>{session.name}</span>
              {org && (
                <span>
                  {" · "}
                  <strong>{org.org_name}</strong>
                  <span style={{ fontSize: "12px", color: "#667085" }}> ({org.role})</span>
                </span>
              )}
            </div>
          )}
        </div>
        {session && (
          <nav className="nav-actions">
            {canGoBack && (
              <button
                type="button"
                className="btn-secondary"
                onClick={handleBack}
                aria-label="Go back to previous screen"
              >
                ← Back
              </button>
            )}
            {org && (
              <button
                type="button"
                className="btn-outline-primary"
                onClick={handleChangeOrg}
              >
                Change Organization
              </button>
            )}
            <button
              type="button"
              className="btn-danger-subtle"
              onClick={handleLogout}
            >
              Sign out
            </button>
          </nav>
        )}
      </header>

      {step === "login" && (
        <Login onDone={handleLoginSuccess} />
      )}
      {step === "org" && (
        <OrgPicker
          orgs={session.organizations}
          onPick={handleSelectOrg}
        />
      )}
      {step === "diagnostic" && (
        <Diagnostic
          draftAnswers={draftAnswers}
          onAnswerChange={(qid, val) =>
            setDraftAnswers((prev) => ({ ...prev, [qid]: val }))
          }
          onSubmissionSuccess={() => setDraftAnswers({})}
          onDone={() => {
            setHistory((prev) => [...prev, "diagnostic"]);
            setStep("report");
          }}
        />
      )}
      {step === "report" && (
        <Report
          onRetake={() => {
            setHistory((prev) => [...prev, "report"]);
            setStep("diagnostic");
          }}
          onDelete={() => setDraftAnswers({})}
        />
      )}
      {step === "dashboard" && (
        <Dashboard org={org} />
      )}
    </div>
  );
}
