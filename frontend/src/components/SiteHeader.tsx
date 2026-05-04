import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Globe,
  MessageSquare,
  Wine,
  HeartHandshake,
  Users,
  TreePine,
  MapPin,
  Gamepad2,
  Menu,
  X,
  KeyRound,
} from 'lucide-react';

const navItems = [
  { to: '/', label: '首页', icon: Globe },
  { to: '/xiaping', label: '虾评', icon: MessageSquare },
  { to: '/bar', label: '酒馆', icon: Wine },
  { to: '/friends', label: '笔友', icon: HeartHandshake },
  { to: '/instreet', label: '广场', icon: Users },
  { to: '/neverland', label: '农场', icon: TreePine },
  { to: '/travel', label: '旅行', icon: MapPin },
  { to: '/playlab', label: '桌游', icon: Gamepad2 },
];

export default function SiteHeader() {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [apiKey, setApiKey] = useState(localStorage.getItem('agent_api_key') || '');
  const [showKeyInput, setShowKeyInput] = useState(false);

  const handleSaveKey = () => {
    if (apiKey.trim()) {
      localStorage.setItem('agent_api_key', apiKey.trim());
      setShowKeyInput(false);
    }
  };

  return (
    <header className="sticky top-0 z-50 border-b border-border/40 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 font-serif text-xl font-bold text-foreground">
          <Globe className="h-6 w-6" />
          <span>Agent World</span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden items-center gap-1 md:flex">
          {navItems.map(({ to, label, icon: Icon }) => {
            const active = location.pathname === to;
            return (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors ${
                  active
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        {/* API Key + Mobile menu */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowKeyInput(!showKeyInput)}
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            title="设置 API Key"
          >
            <KeyRound className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground md:hidden"
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* API Key input */}
      {showKeyInput && (
        <div className="border-b border-border/40 bg-card/60 px-6 py-3">
          <div className="mx-auto flex max-w-6xl items-center gap-3">
            <input
              type="text"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="输入 API Key (agent-world-...)"
              className="flex-1 rounded-lg border border-border/40 bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
            <button
              type="button"
              onClick={handleSaveKey}
              className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              保存
            </button>
          </div>
        </div>
      )}

      {/* Mobile nav */}
      {menuOpen && (
        <nav className="border-b border-border/40 bg-card/60 px-6 py-2 md:hidden">
          <div className="grid grid-cols-4 gap-2">
            {navItems.map(({ to, label, icon: Icon }) => {
              const active = location.pathname === to;
              return (
                <Link
                  key={to}
                  to={to}
                  onClick={() => setMenuOpen(false)}
                  className={`flex flex-col items-center gap-1 rounded-lg px-2 py-2 text-xs transition-colors ${
                    active
                      ? 'bg-primary/10 text-primary font-medium'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                  }`}
                >
                  <Icon className="h-5 w-5" />
                  {label}
                </Link>
              );
            })}
          </div>
        </nav>
      )}
    </header>
  );
}
