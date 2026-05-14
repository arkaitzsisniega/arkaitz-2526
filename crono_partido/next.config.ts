import type { NextConfig } from "next";

// Export estático condicional para desplegar en GitHub Pages.
// Sólo se activa cuando NEXT_EXPORT=1 (lo usa el workflow / build manual).
// En dev (`npm run dev`) sigue siendo el server completo normal.
const isExport = process.env.NEXT_EXPORT === "1";
const basePath = isExport ? "/arkaitz-2526/crono" : "";

const nextConfig: NextConfig = {
  output: isExport ? "export" : undefined,
  basePath: basePath || undefined,
  assetPrefix: basePath || undefined,
  trailingSlash: true,            // GH Pages sirve mejor /ruta/index.html
  images: { unoptimized: true },  // requerido por output: export
};

export default nextConfig;
