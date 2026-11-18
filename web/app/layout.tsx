import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import { Suspense } from "react";

import { Footer } from "@/components/footer";
import { Header } from "@/components/header";
import { RouteFocus } from "@/components/route-focus";
import { ROOT_TITLE, SITE_DESCRIPTION } from "@/lib/metadata";

import "./globals.css";

const archivo = Archivo({
  subsets: ["latin"],
  axes: ["wdth"],
  variable: "--font-archivo",
  display: "swap",
});

export const metadata: Metadata = {
  title: ROOT_TITLE,
  description: SITE_DESCRIPTION,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${archivo.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-paper text-ink">
        <Header />
        {/* Focusable only from code: RouteFocus moves focus here after a navigation. */}
        <main id="main" tabIndex={-1} className="flex-1 outline-none">
          {children}
        </main>
        {/* usePathname is request data: under Cache Components it needs its own boundary. */}
        <Suspense fallback={null}>
          <RouteFocus />
        </Suspense>
        <Footer />
      </body>
    </html>
  );
}
