import React from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";

function App(): JSX.Element {
  return (
    <main className="app-shell">
      <section className="status-panel">
        <p className="eyebrow">Phase 0</p>
        <h1>Global Geopolitical Instability and Trade Impact Platform</h1>
        <p>
          Repository scaffolding is ready. Data ingestion, modeling, and map interaction begin in
          later verified phases.
        </p>
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
