import type { Metadata } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: 'OpenBox Barrier Demo',
  description:
    'Local operator UI for OpenBox-protected LangGraph research workflows.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
