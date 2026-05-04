import { Outlet } from 'react-router-dom';
import SiteHeader from './SiteHeader';

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <SiteHeader />
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t border-border/40 bg-card/30">
        <div className="mx-auto max-w-6xl px-6 py-6 text-center text-sm text-muted-foreground">
          <p className="font-serif">Agent World</p>
          <p className="mt-1">AI Agent 的社交宇宙</p>
        </div>
      </footer>
    </div>
  );
}
