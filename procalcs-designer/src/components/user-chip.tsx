// UserChip — a compact "who did this" badge for diagnostic pages.
//
// Renders as: [colored circle with 2 initials] [optional label text].
// On hover, a tooltip reveals the full email.
//
// Uses the user's email as the unique identity. The initials are
// derived from the email's local-part (before the @). We pick a
// stable colour per email by hashing the address — so the same user
// always shows up as the same colour across all diagnostic pages,
// which lets the eye spot "all of Richard's runs" at a glance.

import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface UserChipProps {
  email: string | null | undefined;
  /** Render the email text next to the avatar. Default true. */
  showText?: boolean;
  /** Compact pill (tiny font, used inside tight table cells). Default false. */
  size?: "sm" | "md";
  className?: string;
}

// Palette — distinct enough that 5-6 users on screen don't collide.
// All tuned to the design system's emerald/indigo/amber/rose/sky/violet
// hues so they sit nicely in both light and dark mode.
const PALETTE = [
  "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 ring-emerald-500/30",
  "bg-indigo-500/20  text-indigo-700  dark:text-indigo-300  ring-indigo-500/30",
  "bg-amber-500/20   text-amber-700   dark:text-amber-300   ring-amber-500/30",
  "bg-rose-500/20    text-rose-700    dark:text-rose-300    ring-rose-500/30",
  "bg-sky-500/20     text-sky-700     dark:text-sky-300     ring-sky-500/30",
  "bg-violet-500/20  text-violet-700  dark:text-violet-300  ring-violet-500/30",
  "bg-teal-500/20    text-teal-700    dark:text-teal-300    ring-teal-500/30",
  "bg-fuchsia-500/20 text-fuchsia-700 dark:text-fuchsia-300 ring-fuchsia-500/30",
];

const UNKNOWN_CLASS =
  "bg-muted text-muted-foreground ring-border";

function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function initialsFor(email: string): string {
  const local = email.split("@")[0] ?? email;
  // "tom.platania" → TP, "richard" → RI, "gerald.villaran" → GV
  const parts = local.split(/[._\-+]/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return local.slice(0, 2).toUpperCase();
}

function shortLabel(email: string): string {
  // Show just the local-part (before @) — keeps cells narrow while
  // still being human-readable. Domain visible on hover.
  return email.split("@")[0] ?? email;
}

export function UserChip({
  email,
  showText = true,
  size = "sm",
  className,
}: UserChipProps) {
  const hasUser = !!(email && email.trim());
  const tone = hasUser
    ? PALETTE[hashStr(email!.toLowerCase()) % PALETTE.length]
    : UNKNOWN_CLASS;

  const avatar = (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-full ring-1 font-semibold shrink-0 leading-none",
        tone,
        size === "sm" ? "w-4 h-4 text-[8px]" : "w-5 h-5 text-[10px]",
      )}
    >
      {hasUser ? initialsFor(email!) : "?"}
    </span>
  );

  const inner = (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 min-w-0",
        size === "sm" ? "text-[11px]" : "text-xs",
        className,
      )}
    >
      {avatar}
      {showText && (
        <span className="truncate text-muted-foreground">
          {hasUser ? shortLabel(email!) : "unknown"}
        </span>
      )}
    </span>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>{inner}</TooltipTrigger>
      <TooltipContent side="top" className="text-xs">
        {hasUser ? email : "No initiator recorded for this run"}
      </TooltipContent>
    </Tooltip>
  );
}
