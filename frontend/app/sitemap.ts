import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL ?? (
    process.env.NODE_ENV === "development" ? "http://127.0.0.1:3000" : ""
  );
  const routes = ["", "/build/generate", "/build/manual"];
  return routes.map((route, index) => ({
    url: `${baseUrl}${route}`,
    lastModified: new Date(),
    changeFrequency: "weekly",
    priority: index === 0 ? 1 : 0.8
  }));
}
