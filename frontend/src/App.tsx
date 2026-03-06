import { DomainMonitorDashboard } from "@/components/domain-monitor-dashboard"
import { ThemeProvider } from "@/components/theme-provider"
import { TooltipProvider } from "@/components/ui/tooltip"

export default function App() {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      storageKey="theme"
    >
      <TooltipProvider>
        <div className="min-h-screen bg-background font-sans text-foreground antialiased">
          <DomainMonitorDashboard />
        </div>
      </TooltipProvider>
    </ThemeProvider>
  )
}
