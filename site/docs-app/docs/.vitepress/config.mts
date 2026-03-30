import { defineConfig } from "vitepress";

export default defineConfig({
  base: "/docs/",
  // `false` removes the toggle and avoids truthy `site.appearance` (e.g. force-dark still
  // satisfies `hasExtraContent` in VPNavBarExtra). Dark class is set via script below.
  appearance: false,
  title: "Pulse Docs",
  description: "Self-hosted Pulse deployment and operations docs.",
  head: [
    [
      "script",
      { id: "pulse-docs-dark" },
      "document.documentElement.classList.add('dark')"
    ],
    ["link", { rel: "icon", href: "/docs/favicon.ico", sizes: "any" }],
    [
      "link",
      { rel: "icon", href: "/docs/pulse-mark.svg", type: "image/svg+xml" }
    ]
  ],
  themeConfig: {
    logo: "/pulse-mark.svg",
    siteTitle: "Pulse Docs",
    nav: [
      // `"/"` is rewritten to `/docs/` under base. `"/../"` yields `/docs/../` → `/`. `target` is required
      // so VitePress does not intercept the click and try to SPA-load `/` (no such page).
      { text: "Main site", link: "/../", target: "_self" },
      { text: "Self-Hosting", link: "/self-hosting/quickstart" },
      { text: "Configuration", link: "/reference/configuration" },
      { text: "Operations", link: "/operations/runbook" },
      { text: "Connectors", link: "/connectors/" }
    ],
    sidebar: [
      {
        text: "Self-Hosting Docs",
        items: [
          { text: "Overview", link: "/" },
          { text: "Self-Hosting Quickstart", link: "/self-hosting/quickstart" },
          {
            text: "MCP agent setup (for AI assistants)",
            link: "/self-hosting/mcp-agent-setup"
          }
        ]
      },
      {
        text: "Configuration",
        items: [{ text: "Configuration Reference", link: "/reference/configuration" }]
      },
      {
        text: "Operations",
        items: [{ text: "Operations Runbook", link: "/operations/runbook" }]
      },
      {
        text: "Connectors",
        items: [{ text: "Connectors Index", link: "/connectors/" }]
      }
    ]
  }
});
