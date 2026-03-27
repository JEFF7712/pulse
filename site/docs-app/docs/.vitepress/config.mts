import { defineConfig } from "vitepress";

export default defineConfig({
  base: "/docs/",
  title: "Pulse Docs",
  description: "Self-hosted Pulse deployment and operations docs.",
  head: [
    ["link", { rel: "preconnect", href: "https://fonts.googleapis.com" }],
    [
      "link",
      {
        rel: "preconnect",
        href: "https://fonts.gstatic.com",
        crossorigin: ""
      }
    ],
    [
      "link",
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist+Mono:wght@300;400&display=swap"
      }
    ]
  ],
  themeConfig: {
    nav: [
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
          { text: "Self-Hosting Quickstart", link: "/self-hosting/quickstart" }
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
