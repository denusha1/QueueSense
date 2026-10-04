import { Pwa } from "../components/pwa";
import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./polish.css";
import "./experience.css";
import "./buttons.css";
import "./advanced.css";
import "./premium.css";
import "./theme.css";
import { ExperienceEffects } from "../components/experience-effects";

export const viewport: Viewport = {themeColor:"#123e34",width:"device-width",initialScale:1};

export const metadata: Metadata = {
  referrer: "no-referrer",
  icons: {apple:"/icons/icon-192.png"},
  appleWebApp: {capable:true,title:"QueueSense",statusBarStyle:"default"},
  title: "QueueSense · Welcome",
  description: "A clearer picture of patient flow. QueueSense healthcare operations platform — synthetic data demonstration.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><head><link rel="preload" href="/fonts/dm-sans-latin.woff2" as="font" type="font/woff2" crossOrigin="anonymous"/><link rel="preload" href="/fonts/manrope-latin.woff2" as="font" type="font/woff2" crossOrigin="anonymous"/></head><body>{children}<ExperienceEffects/><Pwa/></body></html>;
}
