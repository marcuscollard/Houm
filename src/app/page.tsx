import Script from "next/script";

export default function Home() {
  return (
    <>
      <div className="page">
        <header className="topbar">
          <div className="topbar-brand">
            <div className="brand">Houm</div>
            <div className="tagline">
              Empowering homebuyers with the same know-how as a professional
              broker.
            </div>
          </div>
          <div className="topbar-actions">
            <button
              className="cta help-button"
              id="help-button"
              type="button"
              aria-haspopup="dialog"
              aria-expanded="false"
              aria-controls="help-modal"
            >
              Help
            </button>
            <div className="profile">
              <button
                className="profile-button"
                id="profile-button"
                type="button"
                aria-haspopup="dialog"
                aria-expanded="false"
                aria-controls="profile-popover"
                aria-label="Profile"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4zm0 2c-4 0-7 2-7 5v1h14v-1c0-3-3-5-7-5z"
                    fill="currentColor"
                  ></path>
                </svg>
              </button>
              <div
                className="profile-popover hidden"
                id="profile-popover"
                role="dialog"
                aria-label="Profile"
              >
                <form id="profile-form">
                  <label htmlFor="profile-name-input">Your name</label>
                  <input
                    id="profile-name-input"
                    className="profile-input"
                    type="text"
                    placeholder="Type your name"
                    autoComplete="name"
                  />
                  <button className="profile-save" type="submit">
                    Save
                  </button>
                  <div className="profile-greeting" id="profile-greeting">
                    Not signed in
                  </div>
                </form>
              </div>
            </div>
          </div>
        </header>
        <div className="help-modal hidden" id="help-modal" role="dialog" aria-label="How to use Houm">
          <div className="help-card">
            <div className="help-header">
              <h2>How to use Houm</h2>
              <button className="help-close" id="help-close" type="button" aria-label="Close help">
                X
              </button>
            </div>
            <p className="help-subtitle">Quick tips to get the most out of the map.</p>
            <ul className="help-list">
              <li>Pan or zoom to load listings in the visible map area.</li>
              <li>Click a marker to open the full listing panel.</li>
              <li>Ask the assistant for filters like budget, rooms, or parks nearby.</li>
              <li>Sign in with your name to save favorites and preferences.</li>
              <li>Green markers are assistant recommendations with pros/cons on the right.</li>
            </ul>
            <div className="help-actions">
              <button className="cta" id="help-cta" type="button">
                Got it
              </button>
            </div>
          </div>
        </div>

        <main className="content">
          <aside className="assistant-panel">
            <div className="map-query" id="map-query">
              <div className="map-query-header">
                <div className="map-query-title">Assistant</div>
                <button
                  className="map-query-toggle"
                  id="map-query-toggle"
                  type="button"
                  aria-expanded="false"
                >
                  Expand
                </button>
              </div>
              <div
                className="map-query-history"
                id="map-query-history"
                aria-live="polite"
              ></div>
              <form className="map-query-form" id="map-query-form">
                <input
                  id="map-query-input"
                  type="text"
                  placeholder="Ask about listings or parks"
                  autoComplete="off"
                />
                <button type="submit">Send</button>
              </form>
            </div>
          </aside>

          <section className="map-wrap">
            <div id="map" className="map" aria-label="Listings map"></div>
            <div id="map-overlay" className="map-overlay">
              <div className="overlay-card">
                <h2>Connect the map</h2>
                <p id="map-status">
                  Set <span className="mono">GOOGLE_MAPS_API_KEY</span> in
                  <span className="mono">.env</span> and run the backend server
                  to activate the map.
                </p>
              </div>
            </div>
            <div className="map-legend">
              <span className="legend-dot"></span>
              <span>Tap a dot to load the home details.</span>
            </div>
          </section>

          <aside className="listing-panel">
            <div className="listing-media">
              <img
                id="listing-image"
                src="assets/house-placeholder.svg"
                alt="Selected house"
              />
              <div className="price-badge" id="listing-price">
                $1,250,000
              </div>
            </div>
            <div className="listing-body">
              <div className="listing-title" id="listing-title">
                Hammock Bay Villa
              </div>
              <div className="listing-location" id="listing-location">
                Oak Harbor, Stockholm County
              </div>

              <div className="stat-grid">
                <div className="stat">
                  <div className="label">Rooms</div>
                  <div className="value" id="listing-beds">
                    4
                  </div>
                </div>
                <div className="stat">
                  <div className="label">Fee</div>
                  <div className="value" id="listing-baths">
                    3
                  </div>
                </div>
                <div className="stat">
                  <div className="label">Area</div>
                  <div className="value" id="listing-area">
                    210 m2
                  </div>
                </div>
                <div className="stat">
                  <div className="label">Year</div>
                  <div className="value" id="listing-year">
                    2018
                  </div>
                </div>
              </div>

              <div className="features">
                <h3>Highlights</h3>
                <ul id="listing-features"></ul>
              </div>

              <div className="recommendation-notes">
                <h3>Assistant notes</h3>
                <div className="note-group">
                  <h4>Reasons</h4>
                  <ul id="listing-pros" className="note-list"></ul>
                </div>
                <div className="note-group">
                  <h4>Downsides</h4>
                  <ul id="listing-cons" className="note-list"></ul>
                </div>
              </div>

              <div className="cta-group">
                <button className="primary">Schedule tour</button>
                <button className="ghost" id="save-favorite" type="button">
                  Save
                </button>
              </div>
            </div>
          </aside>
        </main>
      </div>
      <Script src="/app.js?v=4" strategy="afterInteractive" />
    </>
  );
}
