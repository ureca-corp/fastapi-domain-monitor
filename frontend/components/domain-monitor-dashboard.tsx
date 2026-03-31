"use client"

import {
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Clock3,
  MoonStar,
  RefreshCw,
  SunMedium,
} from "lucide-react"
import { useTheme } from "next-themes"

import { DiagramCanvas } from "@/components/diagram-canvas"
import { ThemeModeControl } from "@/components/theme-mode-control"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import {
  Sidebar,
  SidebarProvider,
} from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"
import { useIsMobile } from "@/hooks/use-mobile"
import {
  buildAliasMap,
  buildAvailableStereotypes,
  buildDomainSections,
  buildMonitorUrl,
  getMonitorBaseUrl,
  MonitorSchema,
} from "@/lib/monitor"
import { cn } from "@/lib/utils"

export function DomainMonitorDashboard() {
  const isMobile = useIsMobile()
  const { resolvedTheme, theme } = useTheme()
  const initializedDefaultsRef = useRef(false)

  const [monitorBaseUrl, setMonitorBaseUrl] = useState(() => getMonitorBaseUrl())
  const [schema, setSchema] = useState<MonitorSchema | null>(null)
  const [showBaseFields, setShowBaseFields] = useState(true)
  const [selectedDomains, setSelectedDomains] = useState<string[]>([])
  const [activeDomainName, setActiveDomainName] = useState<string | null>(null)
  const [mermaidSource, setMermaidSource] = useState("classDiagram")
  const [refreshing, setRefreshing] = useState(false)
  const [initializing, setInitializing] = useState(true)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [isLeftPanelCollapsed, setIsLeftPanelCollapsed] = useState(false)
  const [selectedStereotypes, setSelectedStereotypes] = useState<string[]>([])

  useEffect(() => {
    setMonitorBaseUrl(getMonitorBaseUrl())
  }, [])

  const domainSections = useMemo(() => buildDomainSections(schema), [schema])
  const availableStereotypes = useMemo(() => buildAvailableStereotypes(schema), [schema])
  const aliasMap = useMemo(() => buildAliasMap(schema), [schema])
  const activeDomainSection = useMemo(
    () => domainSections.find((section) => section.name === activeDomainName) ?? null,
    [activeDomainName, domainSections]
  )

  const ingestSchema = useCallback((nextSchema: MonitorSchema | null) => {
    if (!nextSchema) {
      return
    }

    const nextDomains = buildDomainSections(nextSchema).map((section) => section.name)

    startTransition(() => {
      setSchema(nextSchema)

      if (!initializedDefaultsRef.current) {
        if (typeof nextSchema.defaults?.show_base_fields === "boolean") {
          setShowBaseFields(nextSchema.defaults.show_base_fields)
        }
        initializedDefaultsRef.current = true
      }

      setSelectedDomains((currentDomains) => {
        if (currentDomains.length === 0) {
          return nextDomains
        }

        const filtered = currentDomains.filter((domain) => nextDomains.includes(domain))
        return filtered.length > 0 ? filtered : nextDomains
      })

      const nextStereotypes = buildAvailableStereotypes(nextSchema)
      setSelectedStereotypes((current) => {
        if (current.length === 0) return nextStereotypes
        const filtered = current.filter((s) => nextStereotypes.includes(s))
        return filtered.length > 0 ? filtered : nextStereotypes
      })
    })
  }, [])

  const syncSchema = useCallback(async () => {
    const response = await fetch(buildMonitorUrl(monitorBaseUrl, "api/schema"), {
      cache: "no-store",
    })
    if (!response.ok) {
      throw new Error("Failed to load schema")
    }

    const payload = (await response.json()) as MonitorSchema
    ingestSchema(payload)
  }, [ingestSchema, monitorBaseUrl])

  const refreshMermaid = useCallback(async () => {
    if (!monitorBaseUrl || !schema) {
      return
    }

    if (selectedDomains.length === 0 || selectedStereotypes.length === 0) {
      setMermaidSource("classDiagram")
      return
    }

    const params = new URLSearchParams({
      detail_level: "compact",
      domains: selectedDomains.join(","),
      show_base_fields: String(showBaseFields),
      stereotypes: selectedStereotypes.join(","),
    })

    const response = await fetch(buildMonitorUrl(monitorBaseUrl, `api/mermaid?${params.toString()}`), {
      cache: "no-store",
    })
    if (!response.ok) {
      throw new Error("Failed to load Mermaid diagram")
    }

    setMermaidSource(await response.text())
  }, [monitorBaseUrl, schema, selectedDomains, showBaseFields, selectedStereotypes])

  useEffect(() => {
    if (!monitorBaseUrl) {
      return
    }

    let cancelled = false

    async function bootstrap() {
      setInitializing(true)
      setStatusError(null)

      try {
        await syncSchema()
      } catch (error) {
        if (!cancelled) {
          setStatusError(error instanceof Error ? error.message : String(error))
        }
      } finally {
        if (!cancelled) {
          setInitializing(false)
        }
      }
    }

    void bootstrap()

    return () => {
      cancelled = true
    }
  }, [monitorBaseUrl, syncSchema])

  useEffect(() => {
    if (!monitorBaseUrl || !schema) {
      return
    }

    let cancelled = false

    async function run() {
      try {
        setStatusError(null)
        await refreshMermaid()
      } catch (error) {
        if (!cancelled) {
          setStatusError(error instanceof Error ? error.message : String(error))
        }
      }
    }

    void run()

    return () => {
      cancelled = true
    }
  }, [monitorBaseUrl, refreshMermaid, schema])

  useEffect(() => {
    if (domainSections.length === 0) {
      setActiveDomainName(null)
      return
    }

    if (!activeDomainName || !domainSections.some((section) => section.name === activeDomainName)) {
      setActiveDomainName(domainSections[0]?.name ?? null)
    }
  }, [activeDomainName, domainSections])

  async function handleRefresh() {
    setRefreshing(true)
    try {
      setStatusError(null)
      const response = await fetch(buildMonitorUrl(monitorBaseUrl, "api/refresh"), {
        method: "POST",
        cache: "no-store",
      })
      if (!response.ok) {
        throw new Error("Refresh failed")
      }
      const payload = (await response.json()) as MonitorSchema
      ingestSchema(payload)
      await refreshMermaid()
    } catch (error) {
      setStatusError(error instanceof Error ? error.message : String(error))
    } finally {
      setRefreshing(false)
    }
  }

  const formattedGeneratedAt = schema?.generated_at
    ? new Intl.DateTimeFormat("en-US", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(schema.generated_at))
    : "Waiting for schema"

  const selectedDomainCount = selectedDomains.length
  const themeTone = resolvedTheme === "dark" ? "dark" : "light"
  const currentThemeLabel = theme === "system" ? `System • ${themeTone}` : themeTone === "dark" ? "Dark" : "Light"
  const desktopPanelTopOffset = "top-[6.75rem]"

  const setDomainVisibility = useCallback((domainName: string, nextVisible: boolean) => {
    setSelectedDomains((current) => {
      if (nextVisible) {
        return [...new Set([...current, domainName])].sort((left, right) =>
          left.localeCompare(right)
        )
      }

      return current.filter((item) => item !== domainName)
    })
  }, [])

  const setStereotypeVisibility = useCallback((stereotype: string, nextVisible: boolean) => {
    setSelectedStereotypes((current) => {
      if (nextVisible) {
        return [...new Set([...current, stereotype])].sort((left, right) =>
          left.localeCompare(right)
        )
      }
      return current.filter((item) => item !== stereotype)
    })
  }, [])

  const leftSidebar = (
    <Sidebar
      className="h-full rounded-[28px] border border-sidebar-border/70 bg-sidebar/92 shadow-[0_18px_60px_-42px_rgba(0,0,0,0.7)] backdrop-blur-xl"
      collapsible="none"
    >
      <div className="flex h-full flex-col p-4">
        <div className="space-y-2">
          <p className="text-[11px] font-medium tracking-[0.22em] uppercase text-muted-foreground">
            Current view
          </p>
          <h2 className="font-mono text-xl tracking-[-0.04em]">
            {selectedDomainCount} domain{selectedDomainCount === 1 ? "" : "s"} selected
          </h2>
          <p className="text-sm leading-6 text-muted-foreground">
            Toggle visibility with checkboxes to filter the diagram.
          </p>
        </div>

        <Separator className="my-4 bg-sidebar-border/70" />

        <div className="flex min-h-0 flex-1 flex-col">
          <div>
            <p className="text-[11px] font-medium tracking-[0.22em] uppercase text-muted-foreground">
              Domains
            </p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Checkboxes filter the diagram. Clicking the label selects that domain.
            </p>
          </div>

          <div className="mt-4 min-h-0 flex-1">
            {initializing && domainSections.length === 0 ? (
              <div className="space-y-3">
                {Array.from({ length: 6 }).map((_, index) => (
                  <Skeleton className="h-10 rounded-xl" key={index} />
                ))}
              </div>
            ) : (
              <ScrollArea className="h-full pr-2">
                <div className="space-y-1.5">
                  {domainSections.map((section) => {
                    const checked = selectedDomains.includes(section.name)
                    const isActive = activeDomainName === section.name

                    return (
                      <div
                        className={cn(
                          "flex items-center gap-3 rounded-xl px-2 py-2 transition-colors",
                          isActive && "bg-accent/70"
                        )}
                        key={section.name}
                      >
                        <span
                          className="flex items-center"
                          onClick={(event) => event.stopPropagation()}
                          onPointerDown={(event) => event.stopPropagation()}
                        >
                          <Checkbox
                            checked={checked}
                            onCheckedChange={(nextChecked) => {
                              setDomainVisibility(section.name, Boolean(nextChecked))
                            }}
                          />
                        </span>
                        <button
                          className="min-w-0 flex-1 text-left"
                          onClick={() => setActiveDomainName(section.name)}
                          type="button"
                        >
                          <p className="truncate text-sm font-medium">{section.name}</p>
                          <p className="text-[11px] text-muted-foreground">
                            {section.fileCount} files
                          </p>
                        </button>
                      </div>
                    )
                  })}
                </div>
              </ScrollArea>
            )}
          </div>
        </div>

        {availableStereotypes.length > 0 && (
          <>
            <Separator className="my-4 bg-sidebar-border/70" />
            <div>
              <p className="text-[11px] font-medium tracking-[0.22em] uppercase text-muted-foreground">
                Component types
              </p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                Toggle which component types appear in the diagram.
              </p>
              <div className="mt-3 space-y-1.5">
                {availableStereotypes.map((stereotype) => {
                  const checked = selectedStereotypes.includes(stereotype)
                  return (
                    <div
                      className="flex items-center gap-3 rounded-xl px-2 py-2"
                      key={stereotype}
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={(nextChecked) => {
                          setStereotypeVisibility(stereotype, Boolean(nextChecked))
                        }}
                      />
                      <span className="text-sm font-medium">{stereotype}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          </>
        )}

        <Separator className="my-4 bg-sidebar-border/70" />

        <div className="space-y-4">
          <div>
            <p className="text-[11px] font-medium tracking-[0.22em] uppercase text-muted-foreground">
              Show base fields
            </p>
            <div className="mt-2 flex items-center gap-3">
              <Checkbox
                checked={showBaseFields}
                onCheckedChange={(nextChecked) => setShowBaseFields(Boolean(nextChecked))}
              />
              <span className="text-sm text-muted-foreground">
                Display inherited base fields
              </span>
            </div>
          </div>
        </div>
      </div>
    </Sidebar>
  )

  const diagramCanvas = initializing && !schema ? (
    <div className="grid h-full gap-4 p-6">
      <Skeleton className="h-24 rounded-[28px]" />
      <Skeleton className="flex-1 rounded-[28px]" />
    </div>
  ) : (
    <DiagramCanvas
      aliasMap={aliasMap}
      className={cn(
        "h-full w-full min-h-0 border-0 bg-transparent",
        isMobile ? "rounded-[28px]" : "rounded-none"
      )}
      onSymbolSelect={() => {}}
      selectedSymbolId={null}
      source={mermaidSource}
      theme={resolvedTheme === "dark" ? "dark" : "light"}
    />
  )

  if (isMobile) {
    return (
      <SidebarProvider>
        <div className="relative min-h-screen overflow-hidden bg-background text-foreground">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.22),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(0,0,0,0.08),transparent_28%)] dark:bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.08),transparent_22%),radial-gradient(circle_at_bottom_right,rgba(255,255,255,0.05),transparent_18%)]" />
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(0,0,0,0.025)_1px,transparent_1px),linear-gradient(90deg,rgba(0,0,0,0.025)_1px,transparent_1px)] bg-[size:36px_36px] opacity-60 dark:bg-[linear-gradient(rgba(255,255,255,0.035)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.035)_1px,transparent_1px)]" />

          <div className="relative z-10 flex min-h-screen flex-col">
            <header className="border-b border-border/80 bg-background/90 px-4 py-4 backdrop-blur-xl">
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className="rounded-full border border-border bg-muted/80 px-3 py-1 text-[11px] tracking-[0.22em] uppercase text-muted-foreground" variant="outline">
                    Domain Monitor
                  </Badge>
                  <Badge className="rounded-full bg-primary px-3 py-1 text-[11px] tracking-[0.2em] uppercase text-primary-foreground">
                    shadcn blocks
                  </Badge>
                </div>
                <div>
                  <h1 className="font-mono text-2xl font-semibold tracking-[-0.04em]">
                    Pydantic & SQLModel live diagrams
                  </h1>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    Monitor schema changes, pivot domains instantly, and refresh to re-parse source files.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    className="size-10 rounded-full border-border/70 shadow-sm"
                    disabled={refreshing}
                    onClick={() => {
                      void handleRefresh()
                    }}
                    size="icon"
                    type="button"
                    variant="outline"
                  >
                    <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />
                  </Button>
                  <ThemeModeControl />
                </div>
                <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5">
                    {themeTone === "dark" ? <MoonStar className="size-3.5" /> : <SunMedium className="size-3.5" />}
                    {currentThemeLabel}
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <Clock3 className="size-3.5" />
                    {formattedGeneratedAt}
                  </span>
                </div>
              </div>
            </header>

            <div className="relative z-10 flex flex-1 flex-col gap-3 p-3 pb-6">
              {statusError ? (
                <Alert className="rounded-[28px] border border-destructive/30 bg-card/90">
                  <AlertCircle className="h-4 w-4" />
                  <AlertTitle>Monitor update issue</AlertTitle>
                  <AlertDescription>{statusError}</AlertDescription>
                </Alert>
              ) : null}

              <div className="h-[420px]">{leftSidebar}</div>
              <div className="h-[52vh] overflow-hidden rounded-[28px] border border-border/70 bg-card/72 shadow-sm backdrop-blur-xl">
                {diagramCanvas}
              </div>
            </div>
          </div>
        </div>
      </SidebarProvider>
    )
  }

  return (
    <SidebarProvider>
      <div className="relative h-dvh w-full overflow-hidden bg-background text-foreground">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.22),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(0,0,0,0.08),transparent_28%)] dark:bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.08),transparent_22%),radial-gradient(circle_at_bottom_right,rgba(255,255,255,0.05),transparent_18%)]" />
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(0,0,0,0.025)_1px,transparent_1px),linear-gradient(90deg,rgba(0,0,0,0.025)_1px,transparent_1px)] bg-[size:36px_36px] opacity-60 dark:bg-[linear-gradient(rgba(255,255,255,0.035)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.035)_1px,transparent_1px)]" />

        <div className="absolute inset-x-4 top-4 z-40 rounded-[24px] border border-border/70 bg-background/86 px-4 py-3 shadow-[0_24px_80px_-54px_rgba(0,0,0,0.65)] backdrop-blur-xl">
          <div className="flex items-center justify-between gap-6">
            <div className="min-w-0 flex flex-1 items-center gap-4">
              <div className="flex items-center gap-2">
                <Badge className="rounded-full border border-border bg-muted/80 px-3 py-1 text-[11px] tracking-[0.22em] uppercase text-muted-foreground" variant="outline">
                  Domain Monitor
                </Badge>
                <Badge className="rounded-full bg-primary px-3 py-1 text-[11px] tracking-[0.2em] uppercase text-primary-foreground">
                  shadcn blocks
                </Badge>
              </div>
              <div className="hidden h-6 w-px bg-border/70 xl:block" />
              <div className="min-w-0">
                <h1 className="truncate font-mono text-lg font-semibold tracking-[-0.05em] xl:text-xl">
                  Pydantic & SQLModel live diagrams
                </h1>
                <p className="mt-0.5 truncate text-xs leading-5 text-muted-foreground xl:text-[13px]">
                  Full-screen schema canvas with manual refresh and domain filtering.
                </p>
              </div>
            </div>

            <div className="flex flex-col items-end gap-2">
              <div className="flex flex-wrap items-center justify-end gap-2">
                <Button
                  className="size-10 rounded-full border-border/70 shadow-sm"
                  disabled={refreshing}
                  onClick={() => {
                    void handleRefresh()
                  }}
                  size="icon"
                  type="button"
                  variant="outline"
                >
                  <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />
                </Button>
                <ThemeModeControl />
              </div>
              <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                <span className="inline-flex items-center gap-1.5">
                  {themeTone === "dark" ? <MoonStar className="size-3.5" /> : <SunMedium className="size-3.5" />}
                  {currentThemeLabel}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Clock3 className="size-3.5" />
                  {formattedGeneratedAt}
                </span>
              </div>
            </div>
          </div>
        </div>

        {statusError ? (
          <div className="absolute inset-x-0 top-[7rem] z-40 flex justify-center px-4">
            <Alert className="max-w-3xl rounded-[24px] border border-destructive/30 bg-card/90 shadow-[0_20px_60px_-40px_rgba(0,0,0,0.75)] backdrop-blur-xl">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Monitor update issue</AlertTitle>
              <AlertDescription>{statusError}</AlertDescription>
            </Alert>
          </div>
        ) : null}

        <div className="absolute inset-0 z-10">{diagramCanvas}</div>
        <div
          className={cn(
            "absolute bottom-4 left-4 z-30 transition-[width] duration-300 ease-out",
            desktopPanelTopOffset,
            isLeftPanelCollapsed ? "w-14" : "w-[320px]"
          )}
        >
          {isLeftPanelCollapsed ? (
            <Card className="flex h-full flex-col items-center justify-between rounded-[24px] border-border/70 bg-card/88 py-4 shadow-[0_18px_60px_-42px_rgba(0,0,0,0.7)] backdrop-blur-xl">
              <Button
                aria-label="Expand left panel"
                className="size-9 rounded-full"
                onClick={() => setIsLeftPanelCollapsed(false)}
                size="icon"
                type="button"
                variant="outline"
              >
                <ChevronRight className="size-4" />
              </Button>
              <div className="[writing-mode:vertical-rl] rotate-180 text-[10px] font-medium tracking-[0.28em] uppercase text-muted-foreground">
                Domains
              </div>
              <Badge className="rounded-full border border-border bg-background/80 px-2 py-1 text-[10px]" variant="outline">
                {selectedDomains.length}
              </Badge>
            </Card>
          ) : (
            <div className="relative h-full">
              <div className="absolute right-0 top-4 z-10 translate-x-1/2">
                <Button
                  aria-label="Collapse left panel"
                  className="size-9 rounded-full shadow-sm"
                  onClick={() => setIsLeftPanelCollapsed(true)}
                  size="icon"
                  type="button"
                  variant="outline"
                >
                  <ChevronLeft className="size-4" />
                </Button>
              </div>
              {leftSidebar}
            </div>
          )}
        </div>
      </div>
    </SidebarProvider>
  )
}
