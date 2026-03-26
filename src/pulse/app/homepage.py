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
        --accent: #4ade80;
        --dim: #3a3632;
        --panel: rgba(10, 10, 10, 0.88);
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
        min-height: 100vh;
        display: grid;
        place-items: center;
        width: min(100%, calc(100% - 2rem));
        margin: 0 auto;
        padding: 1rem 0;
      }

      .home-card {
        width: min(560px, 100%);
        display: grid;
        grid-template-columns: 120px 1fr;
        gap: 1.25rem;
        align-items: center;
        border: 1px solid var(--dim);
        background: var(--panel);
        box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
        padding: 1.5rem;
      }

      h1 {
        margin: 0;
        font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
        font-weight: 400;
        letter-spacing: -0.03em;
        font-size: clamp(2.6rem, 7vw, 4rem);
        line-height: 0.92;
      }

      .home-copy {
        min-width: 0;
      }

      .pulse-shell {
        position: relative;
        width: 120px;
        aspect-ratio: 1;
        display: grid;
        place-items: center;
      }

      @keyframes pulseExpand {
        0% {
          transform: scale(0.35);
          opacity: 0.4;
        }

        100% {
          transform: scale(1.75);
          opacity: 0;
        }
      }

      @keyframes dotPulse {
        0%,
        100% {
          transform: scale(1);
          opacity: 0.65;
        }

        50% {
          transform: scale(1.18);
          opacity: 1;
        }
      }

      .pulse-ring,
      .pulse-ring::before,
      .pulse-ring::after {
        content: "";
        position: absolute;
        inset: 0;
        border-radius: 50%;
        border: 1px solid var(--dim);
        animation: pulseExpand 7s ease-out infinite;
      }

      .pulse-ring::before {
        inset: 16%;
        border-color: rgba(196, 191, 184, 0.35);
        animation-delay: 2.3s;
      }

      .pulse-ring::after {
        inset: 32%;
        border-color: rgba(74, 222, 128, 0.65);
        animation-delay: 4.6s;
      }

      .pulse-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: var(--accent);
        box-shadow: 0 0 24px rgba(74, 222, 128, 0.55);
        animation: dotPulse 4.8s ease-in-out infinite;
      }

      .home-list {
        display: grid;
        gap: 0.6rem;
        margin-top: 1rem;
      }

      .home-item {
        border: 1px solid var(--dim);
        padding: 0.45rem 0.7rem;
        background: var(--panel);
        color: var(--white);
      }

      a {
        color: var(--accent);
        text-decoration: none;
      }

      a:hover {
        text-decoration: underline;
      }

      @media (max-width: 760px) {
        main {
          width: min(100%, calc(100% - 1rem));
        }

        .home-card {
          grid-template-columns: 1fr;
          justify-items: center;
          text-align: center;
        }

        .pulse-shell {
          width: 100px;
        }
      }
    </style>
  </head>
  <body>
    <main>
      <section class="home-card">
        <div class="pulse-shell" aria-hidden="true">
          <div class="pulse-ring"></div>
          <div class="pulse-dot"></div>
        </div>
        <div class="home-copy">
          <h1>Pulse</h1>
          <div class="home-list">
            <div class="home-item">server online</div>
            <div class="home-item">self-hosted node</div>
            <div class="home-item"><a href="/health">/health</a></div>
            <div class="home-item">POST /webhooks/telegram</div>
          </div>
        </div>
      </section>
    </main>
  </body>
</html>
"""
