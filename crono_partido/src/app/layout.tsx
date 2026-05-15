import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import AuthGate from "@/components/AuthGate";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Cuando se hace `output: 'export'` con basePath, Next NO prefija
// automáticamente los paths absolutos de manifest/iconos en `metadata`.
// Hay que añadir el prefijo a mano (en dev no hay prefijo, queda igual).
const BP = process.env.NEXT_EXPORT === "1" ? "/arkaitz-2526/crono" : "";

export const metadata: Metadata = {
  title: "Inter Crono",
  description: "Crono de partido en directo para el cuerpo técnico de Movistar Inter FS",
  manifest: `${BP}/manifest.json`,
  appleWebApp: {
    capable: true,
    title: "Inter Crono",
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: [
      { url: `${BP}/icons/icon-192.png`, sizes: "192x192", type: "image/png" },
      { url: `${BP}/icons/icon-512.png`, sizes: "512x512", type: "image/png" },
    ],
    apple: [
      { url: `${BP}/apple-touch-icon.png`, sizes: "180x180", type: "image/png" },
      { url: `${BP}/icons/icon-152.png`, sizes: "152x152", type: "image/png" },
      { url: `${BP}/icons/icon-167.png`, sizes: "167x167", type: "image/png" },
      { url: `${BP}/icons/icon-180.png`, sizes: "180x180", type: "image/png" },
    ],
  },
};

export const viewport: Viewport = {
  themeColor: "#1B5E20",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <AuthGate>{children}</AuthGate>
      </body>
    </html>
  );
}
