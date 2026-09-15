import { Geist } from "next/font/google";
import { LandingPage } from "@/components/landing/landing-page";

// Load Geist directly for the landing page — gives us geistSans.className
// which directly applies the font (no CSS variable indirection needed).
const geistSans = Geist({ subsets: ["latin"] });

export default function Home() {
  return <LandingPage fontClassName={geistSans.className} />;
}
