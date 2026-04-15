import { Link, useLocation } from "wouter";
import { useState } from "react";
import { useTheme } from "next-themes";
import {
  LayoutDashboard,
  Users,
  PlusCircle,
  Settings,
  LogOut,
  Blocks,
  ChevronLeft,
  ChevronRight,
  FileStack,
  Cpu,
  Bell,
  Wifi,
  Database,
  Activity,
  Sun,
  Moon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useCurrentUser, useLogout } from "@/lib/auth-hooks";

interface LayoutProps {
  children: React.ReactNode;
}

// First letter of first word + first letter of last word, or the
// first two chars of the email local-part if the name is absent.
function userInitials(name: string | undefined, email: string | undefined): string {
  const source = name?.trim() || email?.split("@")[0] || "";
  const words = source.split(/\s+/).filter(Boolean);
  if (words.length >= 2) {
    return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  }
  return source.slice(0, 2).toUpperCase() || "??";
}

const navigation = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard, section: "Overview" },
  { name: "All Profiles", href: "/profiles", icon: Users, section: "BOM Management" },
  { name: "New Profile", href: "/profiles/new", icon: PlusCircle, section: "BOM Management" },
  { name: "BOM Engine", href: "/bom-engine", icon: Cpu, section: "Processing" },
  { name: "BOM Output", href: "/bom-output", icon: FileStack, section: "Processing" },
];

const sections = ["Overview", "BOM Management", "Processing"];

export function Layout({ children }: LayoutProps) {
  const [location] = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const { theme, resolvedTheme, setTheme } = useTheme();

  const { data: currentUser } = useCurrentUser();
  const logout = useLogout();

  const activeItem = navigation.find(
    (item) => location === item.href || (item.href !== "/" && location.startsWith(item.href))
  );

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">

      {/* ── Sidebar ─────────────────────────────────── */}
      <aside
        className={cn(
          "flex flex-col shrink-0 border-r border-sidebar-border transition-all duration-300 ease-in-out z-30 relative",
          collapsed ? "w-16" : "w-60"
        )}
        style={{
          background: resolvedTheme === "dark"
            ? "linear-gradient(to bottom, hsl(215,28%,22%) 0%, hsl(215,30%,13%) 60%, hsl(216,33%,8%) 100%)"
            : "linear-gradient(to bottom, hsl(215,25%,32%) 0%, hsl(215,28%,20%) 55%, hsl(216,32%,13%) 100%)"
        }}
      >
        {/* Logo row */}
        <div className={cn(
          "h-14 flex items-center border-b border-sidebar-border shrink-0 overflow-hidden",
          collapsed ? "justify-center px-0" : "px-4 gap-3"
        )}>
          <div className="w-8 h-8 bg-sidebar-primary rounded flex items-center justify-center shrink-0">
            <Blocks className="w-4 h-4 text-sidebar-primary-foreground" />
          </div>
          {!collapsed && (
            <span className="font-semibold text-sidebar-foreground tracking-tight text-sm whitespace-nowrap overflow-hidden">
              Designer Desktop
            </span>
          )}
        </div>

        {/* Nav items */}
        <nav className="flex-1 overflow-y-auto py-4 px-2">
          {sections.map((section) => {
            const items = navigation.filter((n) => n.section === section);
            return (
              <div key={section} className="mb-4">
                {!collapsed && (
                  <h4 className="px-3 text-[10px] font-semibold tracking-widest text-sidebar-foreground/40 uppercase mb-1">
                    {section}
                  </h4>
                )}
                {collapsed && <div className="h-3" />}
                <div className="space-y-0.5">
                  {items.map((item) => {
                    const isActive =
                      location === item.href ||
                      (item.href !== "/" && location.startsWith(item.href));

                    const linkEl = (
                      <Link key={item.name} href={item.href}>
                        <span
                          className={cn(
                            "flex items-center gap-3 rounded-md transition-colors cursor-pointer group",
                            collapsed ? "justify-center p-2" : "px-3 py-2 text-sm",
                            isActive
                              ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                              : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                          )}
                        >
                          <item.icon className={cn(
                            "shrink-0",
                            collapsed ? "w-5 h-5" : "w-4 h-4",
                            isActive
                              ? "text-sidebar-accent-foreground"
                              : "text-sidebar-foreground/40 group-hover:text-sidebar-foreground/70"
                          )} />
                          {!collapsed && item.name}
                        </span>
                      </Link>
                    );

                    return collapsed ? (
                      <Tooltip key={item.name} delayDuration={0}>
                        <TooltipTrigger asChild>{linkEl}</TooltipTrigger>
                        <TooltipContent side="right" className="font-medium text-xs">
                          {item.name}
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      linkEl
                    );
                  })}
                </div>
              </div>
            );
          })}
        </nav>

        {/* Bottom actions */}
        <div className={cn(
          "border-t border-sidebar-border py-3 px-2 space-y-0.5 shrink-0",
        )}>
          {[
            { icon: Settings, label: "Settings", onClick: () => {} },
            {
              icon: LogOut,
              label: "Logout",
              onClick: () => logout.mutate(),
            },
          ].map(({ icon: Icon, label, onClick }) =>
            collapsed ? (
              <Tooltip key={label} delayDuration={0}>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="w-full h-9 text-sidebar-foreground/50 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                    onClick={onClick}
                  >
                    <Icon className="w-4 h-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right" className="text-xs">{label}</TooltipContent>
              </Tooltip>
            ) : (
              <Button
                key={label}
                variant="ghost"
                className="w-full justify-start text-sm text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                onClick={onClick}
              >
                <Icon className="w-4 h-4 mr-2" />
                {label}
              </Button>
            )
          )}
        </div>

        {/* Collapse toggle */}
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="absolute -right-3 top-[52px] z-40 w-6 h-6 rounded-full bg-sidebar-primary text-sidebar-primary-foreground flex items-center justify-center shadow-md hover:scale-110 transition-transform"
        >
          {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
        </button>
      </aside>

      {/* ── Right column ───────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">

        {/* Fixed top nav — glass effect */}
        <header className="h-14 shrink-0 flex items-center justify-between px-6 sticky top-0 z-20 backdrop-blur-md bg-background/75 border-b border-border/60 shadow-sm">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">BOM Control Center</span>
            <span className="text-border">/</span>
            <span className="font-medium text-foreground">
              {activeItem?.name ?? "Dashboard"}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Notification bell */}
            <Button variant="ghost" size="icon" className="relative h-8 w-8 text-muted-foreground hover:text-foreground">
              <Bell className="w-4 h-4" />
              <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-primary" />
            </Button>

            {/* Theme toggle */}
            <Tooltip delayDuration={0}>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-foreground"
                  onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                >
                  {theme === "dark"
                    ? <Sun className="w-4 h-4" />
                    : <Moon className="w-4 h-4" />
                  }
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-xs">
                {theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              </TooltipContent>
            </Tooltip>

            {/* Avatar */}
            <Tooltip delayDuration={0}>
              <TooltipTrigger asChild>
                {currentUser?.picture ? (
                  <img
                    src={currentUser.picture}
                    alt={currentUser.name}
                    referrerPolicy="no-referrer"
                    className="w-8 h-8 rounded-full border border-primary/20 object-cover"
                  />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-primary/15 border border-primary/20 flex items-center justify-center text-primary font-semibold text-xs">
                    {userInitials(currentUser?.name, currentUser?.email)}
                  </div>
                )}
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-xs">
                <div>{currentUser?.name ?? "Signed in"}</div>
                {currentUser?.email && (
                  <div className="text-muted-foreground">{currentUser.email}</div>
                )}
              </TooltipContent>
            </Tooltip>
          </div>
        </header>

        {/* Scrollable content area */}
        <main className="flex-1 overflow-y-auto p-6 lg:p-8">
          {children}
        </main>

        {/* Fixed footer — status bar */}
        <footer className="h-8 shrink-0 flex items-center justify-between px-5 border-t border-border/50 bg-background/80 backdrop-blur-sm text-[11px] text-muted-foreground">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5">
              <Activity className="w-3 h-3 text-green-500" />
              BOM Engine Active
            </span>
            <span className="flex items-center gap-1.5">
              <Database className="w-3 h-3 text-blue-400" />
              DB Connected
            </span>
            <span className="flex items-center gap-1.5">
              <Wifi className="w-3 h-3 text-green-400" />
              API Online
            </span>
          </div>
          <div className="flex items-center gap-4">
            <span>Designer Desktop v2.1</span>
            <span className="text-border">|</span>
            <span>WrightSoft BOM Integration</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
