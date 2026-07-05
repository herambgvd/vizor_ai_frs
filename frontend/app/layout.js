import "simplebar-react/dist/simplebar.min.css";
import "./scss/app.scss";
import "@/web/theme.css";

import { GeistSans } from "geist/font/sans";

import Providers from "@/web/Providers";

export const metadata = {
  title: "Neubit",
  description: "Neubit — face recognition platform",
};

// Set the theme class before first paint to avoid a flash (reads localStorage).
const noFlashScript = `
try {
  var t = localStorage.getItem('theme');
  document.documentElement.classList.toggle('dark', t !== 'light');
} catch (e) { document.documentElement.classList.add('dark'); }
`;

// Root font-size 14px keeps the whole UI compact (all rem-based sizing scales down).
export default function RootLayout({ children }) {
  return (
    <html lang="en" className="dark" style={{ fontSize: "14px" }} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: noFlashScript }} />
      </head>
      <body className={`${GeistSans.className} antialiased bg-background text-foreground`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
