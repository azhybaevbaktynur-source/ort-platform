import React from "react";
import "@/styles/globals.css";

export const metadata = {
  title: "ОРТ / ЖРТ Даярдоо Платформасы",
  description: "Кыргызстандын окуучулары үчүн бекер ЖРТ даярдоо жана сыноо платформасы",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html>
      <head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.css"
          crossOrigin="anonymous"
        />
      </head>
      <body suppressHydrationWarning className="min-h-screen bg-slate-50 antialiased font-sans">
        {children}
      </body>
    </html>
  );
}

