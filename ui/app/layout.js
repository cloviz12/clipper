import "./globals.css";

export const metadata = { title: "CLIPPER — clips en tiempo real", description: "Panel del equipo" };

export default function Layout({ children }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
