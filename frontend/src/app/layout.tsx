import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/AppShell";
import { ProjectProvider } from "@/components/ProjectProvider";

export const metadata: Metadata = {
  title: "AI PMO",
  description: "Projectの異常を発見し、失敗する前に打ち手を提示するProject Management OS",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <ProjectProvider>
          <AppShell>{children}</AppShell>
        </ProjectProvider>
      </body>
    </html>
  );
}
