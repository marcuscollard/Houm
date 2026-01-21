import "./globals.css";

export const metadata = {
  title: "Houm | Map-first listings",
  description:
    "Map-first real-estate concept UI with a lightweight frontend and smart recommendations."
};

export const viewport = {
  width: "device-width",
  initialScale: 1
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  return (
    <html lang="en">
      <body data-api-base={apiBase}>{children}</body>
    </html>
  );
}
