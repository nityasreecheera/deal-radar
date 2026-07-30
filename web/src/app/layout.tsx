import type { Metadata } from "next";
import { Inter, Newsreader } from "next/font/google";

import "./globals.css";

// A serif for the wordmark and company names, a sans for everything else. The
// mix is what stops a dense list of figures reading like a spreadsheet.
const newsreader = Newsreader({
  subsets: ["latin"],
  weight: ["400", "500"],
  style: ["normal", "italic"],
  variable: "--font-newsreader",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Deal Radar",
  description: "Newly visible companies you have not seen.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${newsreader.variable} ${inter.variable}`}>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
