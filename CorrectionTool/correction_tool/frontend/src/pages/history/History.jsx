import "./history.css";
import { useState, useEffect } from "react";
import { API_URL } from "../../constants";

export default function History() {
  const [analytics, setAnalytics] = useState(null);
  const [selected, setSelected] = useState("");

  useEffect(() => {
    fetch(`${API_URL}/get_analytics`)
      .then((r) => r.json())
      .then(({ analytics }) => {
        setAnalytics(analytics);
        setSelected(Object.keys(analytics)[0] || "");
      })
      .catch(console.error);
  }, []);

  if (!analytics) {
    return (
      <div className="analytics-container">
        <h1>History</h1>
        <p>Loading…</p>
      </div>
    );
  }

  const stats = analytics[selected] || {};
  const users = stats.total_corrected_by_user || {};

  return (
    <div className="analytics-container">
      <h1>History</h1>

      <div className="controls">
        <label htmlFor="project-select">Project:</label>
        <select
          id="project-select"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          {Object.keys(analytics).map((proj) => (
            <option key={proj} value={proj}>
              {proj}
            </option>
          ))}
        </select>
      </div>

      {!stats.total_docs && stats.total_docs !== 0 ? (
        <p className="no-data">No data for this project.</p>
      ) : (
        <>
          <div className="overview">
            <div className="stat">
              <div className="label">Total docs</div>
              <div className="value">{stats.total_docs}</div>
            </div>
            <div className="stat">
              <div className="label">Corrected</div>
              <div className="value">{stats.total_corrected}</div>
            </div>
            <div className="stat">
              <div className="label">Completion</div>
              <div className="progress">
                <div
                  className="progress-bar"
                  style={{ width: `${stats.completion_percentage}%` }}
                >
                  {stats.completion_percentage.toFixed(1)}%
                </div>
              </div>
            </div>
          </div>

          <h2>User contributions</h2>
          <ul className="users-list">
            {Object.entries(users).map(([user, count]) => {
              const pct = stats.total_docs
                ? (count / stats.total_docs) * 100
                : 0;
              return (
                <li key={user} className="user-item">
                  <span className="user-name">{user}</span>
                  <div className="progress small">
                    <div
                      className="progress-bar"
                      style={{ width: `${pct}%` }}
                    >
                      {pct.toFixed(0)}%
                    </div>
                  </div>
                  <span className="count">{count}</span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
