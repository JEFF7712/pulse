from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class HomepageStatus:
    database_path: str
    vault_path: str
    timezone: str
    scheduler_job_count: int
    pull_connectors: int
    push_connectors: int


@dataclass(frozen=True)
class HomepageNotice:
    tone: str
    message: str


def render_homepage(
    status: HomepageStatus,
    notice: HomepageNotice | None = None,
) -> str:
    status_items = "".join(
        (
            _render_status_item("database", status.database_path),
            _render_status_item("vault", status.vault_path),
            _render_status_item("timezone", status.timezone),
            _render_status_item(
                "scheduler", f"configured · {status.scheduler_job_count} jobs"
            ),
            _render_status_item(
                "connectors",
                f"pull {status.pull_connectors} · push {status.push_connectors}",
            ),
        )
    )
    action_labels = "".join(
        (
            _render_action_form("/actions/pull", "run pull"),
            _render_action_form("/actions/digest", "run digest"),
            _render_action_form("/actions/discover", "run discovery"),
            _render_action_form("/actions/test-telegram", "test telegram"),
        )
    )
    notice_markup = ""
    if notice is not None:
        notice_markup = (
            f'<div class="notice notice-{escape(notice.tone)}" '
            f'role="status">{escape(notice.message)}</div>'
        )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Pulse</title>
    <style>
      :root {{
        --black: #050505;
        --white: #e8e4df;
        --accent: #4ade80;
        --dim: #3a3632;
        --panel: rgba(10, 10, 10, 0.88);
        --panel-strong: rgba(15, 15, 15, 0.96);
      }}

      * {{
        box-sizing: border-box;
      }}

      body {{
        margin: 0;
        min-height: 100vh;
        background:
          radial-gradient(circle at top, rgba(74, 222, 128, 0.14), transparent 28%),
          linear-gradient(180deg, #090908 0%, var(--black) 100%);
        color: var(--white);
        font-family: "SFMono-Regular", "Consolas", "Liberation Mono", monospace;
      }}

      body::before {{
        content: "";
        position: fixed;
        inset: 0;
        background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 128 128' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='1.1' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E");
        pointer-events: none;
      }}

      main {{
        position: relative;
        z-index: 1;
        min-height: 100vh;
        display: grid;
        place-items: center;
        width: min(100%, calc(100% - 2rem));
        margin: 0 auto;
        padding: 1rem 0;
      }}

      .home-card {{
        width: min(720px, 100%);
        display: grid;
        grid-template-columns: 120px 1fr;
        gap: 1.25rem;
        align-items: start;
        border: 1px solid var(--dim);
        background: var(--panel);
        box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
        padding: 1.5rem;
      }}

      h1,
      h2 {{
        margin: 0;
      }}

      h1 {{
        font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
        font-weight: 400;
        letter-spacing: -0.03em;
        font-size: clamp(2.6rem, 7vw, 4rem);
        line-height: 0.92;
      }}

      h2 {{
        font-size: 0.8rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: rgba(232, 228, 223, 0.7);
      }}

      .home-copy {{
        min-width: 0;
      }}

      .pulse-shell {{
        position: relative;
        width: 120px;
        aspect-ratio: 1;
        display: grid;
        place-items: center;
      }}

      @keyframes pulseExpand {{
        0% {{
          transform: scale(0.35);
          opacity: 0.4;
        }}

        100% {{
          transform: scale(1.75);
          opacity: 0;
        }}
      }}

      @keyframes dotPulse {{
        0%,
        100% {{
          transform: scale(1);
          opacity: 0.65;
        }}

        50% {{
          transform: scale(1.18);
          opacity: 1;
        }}
      }}

      .pulse-ring,
      .pulse-ring::before,
      .pulse-ring::after {{
        content: "";
        position: absolute;
        inset: 0;
        border-radius: 50%;
        border: 1px solid var(--dim);
        animation: pulseExpand 7s ease-out infinite;
      }}

      .pulse-ring::before {{
        inset: 16%;
        border-color: rgba(196, 191, 184, 0.35);
        animation-delay: 2.3s;
      }}

      .pulse-ring::after {{
        inset: 32%;
        border-color: rgba(74, 222, 128, 0.65);
        animation-delay: 4.6s;
      }}

      .pulse-dot {{
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: var(--accent);
        box-shadow: 0 0 24px rgba(74, 222, 128, 0.55);
        animation: dotPulse 4.8s ease-in-out infinite;
      }}

      .home-list,
      .status-grid {{
        display: grid;
        gap: 0.6rem;
      }}

      .home-list {{
        margin-top: 1rem;
      }}

      .home-item,
      .status-item,
      .action-panel {{
        border: 1px solid var(--dim);
        background: var(--panel-strong);
        color: var(--white);
      }}

      .home-item {{
        padding: 0.45rem 0.7rem;
      }}

      .home-sections {{
        display: grid;
        gap: 1rem;
        margin-top: 1rem;
      }}

      .notice {{
        border: 1px solid var(--dim);
        padding: 0.65rem 0.8rem;
        font-size: 0.9rem;
        line-height: 1.4;
        white-space: pre-wrap;
      }}

      .notice-success {{
        background: rgba(74, 222, 128, 0.12);
        color: #b4f5cb;
        border-color: rgba(74, 222, 128, 0.35);
      }}

      .notice-error {{
        background: rgba(248, 113, 113, 0.12);
        color: #fecaca;
        border-color: rgba(248, 113, 113, 0.35);
      }}

      .status-panel,
      .action-panel {{
        display: grid;
        gap: 0.75rem;
        padding: 0.85rem 0.9rem;
      }}

      .status-item {{
        padding: 0.6rem 0.7rem;
      }}

      .status-label {{
        display: block;
        font-size: 0.72rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgba(232, 228, 223, 0.62);
        margin-bottom: 0.2rem;
      }}

      .status-value {{
        display: block;
        line-height: 1.4;
        word-break: break-word;
      }}

      .action-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
      }}

      .action-form {{
        margin: 0;
      }}

      .action-button {{
        background: rgba(74, 222, 128, 0.08);
        border: 1px solid rgba(74, 222, 128, 0.35);
        padding: 0.4rem 0.65rem;
        color: var(--accent);
        font: inherit;
        cursor: pointer;
      }}

      .action-button:hover {{
        background: rgba(74, 222, 128, 0.14);
      }}

      a {{
        color: var(--accent);
        text-decoration: none;
      }}

      a:hover {{
        text-decoration: underline;
      }}

      @media (max-width: 760px) {{
        main {{
          width: min(100%, calc(100% - 1rem));
        }}

        .home-card {{
          grid-template-columns: 1fr;
          justify-items: center;
          text-align: center;
        }}

        .pulse-shell {{
          width: 100px;
        }}

        .action-row {{
          justify-content: center;
        }}
      }}
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
          <div class="home-sections">
            {notice_markup}
            <section class="status-panel">
              <h2>operator console</h2>
              <div class="status-grid">{status_items}</div>
            </section>
            <section class="action-panel">
              <h2>actions</h2>
              <div class="action-row">{action_labels}</div>
            </section>
          </div>
        </div>
      </section>
    </main>
  </body>
</html>
"""


def _render_status_item(label: str, value: str) -> str:
    return (
        '<div class="status-item">'
        f'<span class="status-label">{escape(label)}</span>'
        f'<span class="status-value">{escape(value)}</span>'
        "</div>"
    )


def _render_action_form(action: str, label: str) -> str:
    return (
        f'<form class="action-form" method="post" action="{escape(action)}">'
        f'<button class="action-button" type="submit">{escape(label)}</button>'
        "</form>"
    )
