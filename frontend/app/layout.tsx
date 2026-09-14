import type { Metadata } from "next";
import "./globals.css";
import "./polish.css";
import "./experience.css";
import "./buttons.css";

export const metadata: Metadata = {
  title: "QueueSense · Welcome",
  description: "A clearer picture of patient flow. QueueSense healthcare operations platform — synthetic data demonstration.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
