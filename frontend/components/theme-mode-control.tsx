"use client"

import { ChevronDown, LaptopMinimal, MoonStar, SunMedium } from "lucide-react"
import { useTheme } from "next-themes"

import { AnimatedThemeToggler } from "@/components/ui/animated-theme-toggler"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

type ThemeMode = "light" | "dark" | "system"

const THEME_LABELS: Record<ThemeMode, string> = {
  dark: "Dark",
  light: "Light",
  system: "System",
}

export function ThemeModeControl() {
  const { resolvedTheme, setTheme, theme } = useTheme()

  const currentTheme = (theme ?? "system") as ThemeMode
  const isDark = resolvedTheme === "dark"
  const label = THEME_LABELS[currentTheme] ?? "System"

  return (
    <div className="flex items-center gap-2">
      <AnimatedThemeToggler
        aria-label="Toggle light and dark theme"
        className="flex size-9 items-center justify-center rounded-full border border-border/70 bg-background text-foreground shadow-sm transition hover:bg-accent"
        isDark={isDark}
        onToggle={() => setTheme(isDark ? "light" : "dark")}
      />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            className="h-9 rounded-full border-border/70 px-3 shadow-sm"
            size="sm"
            variant="outline"
          >
            {currentTheme === "system" ? (
              <LaptopMinimal className="size-4" />
            ) : currentTheme === "dark" ? (
              <MoonStar className="size-4" />
            ) : (
              <SunMedium className="size-4" />
            )}
            <span>{label}</span>
            <ChevronDown className="size-4 text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-44">
          <DropdownMenuRadioGroup
            onValueChange={(value) => setTheme(value as ThemeMode)}
            value={currentTheme}
          >
            <DropdownMenuRadioItem value="light">
              <SunMedium className="size-4" />
              Light
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="dark">
              <MoonStar className="size-4" />
              Dark
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="system">
              <LaptopMinimal className="size-4" />
              System
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
          <DropdownMenuSeparator />
          <div className="px-2 py-1.5">
            <Badge
              className="w-full justify-center rounded-full border-border/70 text-[11px] tracking-[0.18em] uppercase"
              variant="outline"
            >
              {currentTheme === "system"
                ? `following ${isDark ? "dark" : "light"}`
                : `${label} mode`}
            </Badge>
          </div>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
