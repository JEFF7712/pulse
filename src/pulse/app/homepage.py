def render_homepage() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Pulse</title>
    <style>
      :root {
        --black: #050505;
        --white: #e8e4df;
        --cream: #c4bfb8;
        --accent: #4ade80;
        --dim: #3a3632;
        --panel: rgba(14, 13, 11, 0.88);
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        min-height: 100vh;
        background:
          radial-gradient(circle at top, rgba(74, 222, 128, 0.14), transparent 28%),
          linear-gradient(180deg, #090908 0%, var(--black) 100%);
        color: var(--white);
        font-family: "SFMono-Regular", "Consolas", "Liberation Mono", monospace;
      }

      body::before {
        content: "";
        position: fixed;
        inset: 0;
        background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 128 128' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='1.1' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E");
        pointer-events: none;
      }

      main {
        position: relative;
        z-index: 1;
        width: min(960px, calc(100% - 2rem));
        margin: 0 auto;
        padding: 2rem 0 3rem;
      }

      .frame {
        border: 1px solid var(--dim);
        background: rgba(5, 5, 5, 0.78);
        box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
      }

      .hero {
        display: grid;
        grid-template-columns: 180px 1fr;
        gap: 1.5rem;
        align-items: center;
        padding: 1.5rem;
      }

      .hero-copy {
        min-width: 0;
      }

      .eyebrow,
      .section-label,
      .endpoint-label {
        font-size: 0.72rem;
        letter-spacing: 0.24em;
        text-transform: uppercase;
      }

      .eyebrow,
      .section-label {
        color: var(--cream);
      }

      .hero h1,
      .overview h2 {
        margin: 0;
        font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
        font-weight: 400;
        letter-spacing: -0.03em;
      }

      .hero h1 {
        margin-top: 0.6rem;
        font-size: clamp(2.8rem, 7vw, 4.8rem);
        line-height: 0.92;
      }

      .hero p,
      .overview p,
      .endpoint-card p {
        margin: 0;
        color: var(--cream);
        line-height: 1.6;
      }

      .hero p {
        max-width: 34rem;
        margin-top: 0.9rem;
      }

      .pulse-shell {
        position: relative;
        width: 180px;
        aspect-ratio: 1;
        display: grid;
        place-items: center;
      }

      .pulse-ring,
      .pulse-ring::before,
      .pulse-ring::after {
        content: "";
        position: absolute;
        inset: 0;
        border-radius: 50%;
        border: 1px solid var(--dim);
      }

      .pulse-ring::before {
        inset: 16%;
        border-color: rgba(196, 191, 184, 0.35);
      }

      .pulse-ring::after {
        inset: 32%;
        border-color: rgba(74, 222, 128, 0.65);
      }

      .pulse-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: var(--accent);
        box-shadow: 0 0 24px rgba(74, 222, 128, 0.55);
      }

      .hero-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin-top: 1.2rem;
      }

      .status-chip,
      .tag {
        border: 1px solid var(--dim);
        padding: 0.45rem 0.7rem;
        background: var(--panel);
      }

      .status-chip {
        color: var(--white);
      }

      .status-chip strong,
      .endpoint-card a {
        color: var(--accent);
      }

      .overview {
        display: grid;
        grid-template-columns: 1.3fr 0.9fr;
        gap: 1px;
        margin-top: 1px;
        background: var(--dim);
      }

      .overview-copy,
      .overview-stats,
      .endpoint-card {
        background: var(--black);
      }

      .overview-copy,
      .overview-stats {
        padding: 1.5rem;
      }

      .overview h2 {
        margin-top: 0.65rem;
        font-size: clamp(1.6rem, 3vw, 2.2rem);
        line-height: 1.1;
      }

      .stats-list {
        display: grid;
        gap: 1rem;
      }

      .stat {
        padding-top: 1rem;
        border-top: 1px solid var(--dim);
      }

      .stat strong {
        display: block;
        margin-bottom: 0.35rem;
        color: var(--white);
        font-size: 0.82rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
      }

      .endpoints {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 1px;
        margin-top: 1px;
        background: var(--dim);
      }

      .endpoint-card {
        padding: 1.5rem;
      }

      .endpoint-card h3 {
        margin: 0.7rem 0 0.8rem;
        font-size: 1rem;
        font-weight: 400;
        color: var(--white);
      }

      .endpoint-card a {
        text-decoration: none;
      }

      .endpoint-card a:hover {
        text-decoration: underline;
      }

      @media (max-width: 760px) {
        main {
          width: min(100%, calc(100% - 1rem));
          padding: 0.5rem 0 1rem;
        }

        .hero,
        .overview,
        .endpoints {
          grid-template-columns: 1fr;
        }

        .pulse-shell {
          width: 140px;
          margin: 0 auto;
        }

        .hero {
          text-align: center;
        }

        .hero p {
          max-width: none;
        }

        .hero-meta {
          justify-content: center;
        }
      }
    </style>
  </head>
  <body>
    <main>
      <section class="frame hero">
        <div class="pulse-shell" aria-hidden="true">
          <div class="pulse-ring"></div>
          <div class="pulse-dot"></div>
        </div>
        <div class="hero-copy">
          <div class="eyebrow">Operator homepage</div>
          <h1>Pulse</h1>
          <p>Server online for a self-hosted Pulse node with a small control surface for health checks, webhook intake, and quick operator context.</p>
          <div class="hero-meta">
            <div class="status-chip">Status: <strong>server online</strong></div>
            <div class="tag">Mode: self-hosted</div>
          </div>
        </div>
      </section>

      <section class="overview">
        <div class="overview-copy">
          <div class="section-label">Operator overview</div>
          <h2>Compact visibility for the runtime entrypoints that matter.</h2>
          <p>Use this page as the quick-read landing surface for local deployments: confirm the app is reachable, verify the health probe, and keep the Telegram webhook path close at hand.</p>
        </div>
        <div class="overview-stats">
          <div class="stats-list">
            <div class="stat">
              <strong>Runtime</strong>
              <p>FastAPI app serving a static operator UI with no template engine or asset pipeline.</p>
            </div>
            <div class="stat">
              <strong>Surface</strong>
              <p>Health and webhook routes stay visible so a self-hosted operator can validate the node quickly.</p>
            </div>
          </div>
        </div>
      </section>

      <section class="endpoints">
        <article class="endpoint-card">
          <div class="endpoint-label">Endpoint</div>
          <h3><a href="/health">/health</a></h3>
          <p>Check the service heartbeat and confirm the API responds before deeper diagnostics.</p>
        </article>
        <article class="endpoint-card">
          <div class="endpoint-label">Webhook</div>
          <h3>POST /webhooks/telegram</h3>
          <p>Receives Telegram reply webhooks for operator feedback and correction ingestion.</p>
        </article>
      </section>
    </main>
  </body>
</html>
"""
