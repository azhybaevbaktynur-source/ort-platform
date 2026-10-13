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
      <body suppressHydrationWarning className="min-h-screen bg-slate-50 antialiased font-sans">
        {children}
      </body>
    </html>
  );
}

