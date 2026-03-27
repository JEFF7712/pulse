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
        href: "https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist+Mono:wght@300;400&family=Source+Sans+3:ital,wght@0,400;0,500;0,600;1,400&display=swap"
      }
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
      { text: "Website", link: "/" },
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
