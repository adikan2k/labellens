import type { Metadata } from "next";
import { Archivo } from "next/font/google";

import { Footer } from "@/components/footer";
import { Header } from "@/components/header";
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
        <main id="main" className="flex-1">
          {children}
        </main>
        <Footer />
      </body>
    </html>
  );
}
