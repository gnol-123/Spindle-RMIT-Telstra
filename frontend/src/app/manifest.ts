import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Spindle",
    short_name: "Spindle",
    start_url: "/",
    display: "standalone",
    background_color: "#0A0F24",
    theme_color: "#0A0F24",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml" },
      { src: "/apple-icon.png", sizes: "180x180", type: "image/png" },
    ],
  };
}
