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
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  MoonStar,
  RefreshCw,
  ServerCrash,
  SunMedium,
} from "lucide-react"
import { useTheme } from "next-themes"

import { DiagramCanvas } from "@/components/diagram-canvas"
import { ThemeModeControl } from "@/components/theme-mode-control"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { File, Folder, Tree, type TreeViewElement } from "@/components/ui/file-tree"
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
  buildDomainSections,
  buildMonitorUrl,
  buildMonitorWebSocketUrl,
  ConnectionState,
  getMonitorBaseUrl,
  MonitorFileSource,
  MonitorSchema,
  MonitorSource,
} from "@/lib/monitor"
import { cn } from "@/lib/utils"

const MAX_RETRY_DELAY = 30_000

type DomainExplorerNode = {
  id: string
  kind: "directory" | "file"
  name: string
  path?: string
  children?: DomainExplorerNode[]
}

function sortExplorerNodes(nodes: DomainExplorerNode[]): DomainExplorerNode[] {
  return [...nodes]
    .map((node) => ({
      ...node,
      children: node.children ? sortExplorerNodes(node.children) : undefined,
    }))
    .sort((left, right) => {
      if (left.kind !== right.kind) {
        return left.kind === "directory" ? -1 : 1
      }
      return left.name.localeCompare(right.name)
    })
}

function buildDomainExplorerNodes(
  files: Array<{ id: string; path: string | null; relativePath: string }>
): DomainExplorerNode[] {
  const rootNodes: DomainExplorerNode[] = []

  for (const file of files) {
    if (!file.path) {
      continue
    }

    const segments = file.relativePath.split("/").filter(Boolean)
    if (segments.length === 0) {
      continue
    }

    let currentLevel = rootNodes
    let currentKey = ""

    for (const [index, segment] of segments.entries()) {
      const isLeaf = index === segments.length - 1
      const segmentKey = currentKey ? `${currentKey}/${segment}` : segment

      if (isLeaf) {
        currentLevel.push({
          id: `file:${file.id}`,
          kind: "file",
          name: segment,
          path: file.path,
        })
        continue
      }

      let nextNode = currentLevel.find(
        (node) => node.kind === "directory" && node.name === segment
      )
      if (!nextNode) {
        nextNode = {
          id: `dir:${segmentKey}`,
          kind: "directory",
          name: segment,
          children: [],
        }
        currentLevel.push(nextNode)
      }

      currentLevel = nextNode.children ?? []
      nextNode.children = currentLevel
      currentKey = segmentKey
    }
  }

  return sortExplorerNodes(rootNodes)
}

function buildTreeElements(nodes: DomainExplorerNode[]): TreeViewElement[] {
  return nodes.map((node) => ({
    id: node.id,
    name: node.name,
    children: node.children ? buildTreeElements(node.children) : undefined,
  }))
}

export function DomainMonitorDashboard() {
  const isMobile = useIsMobile()
  const { resolvedTheme, theme } = useTheme()
  const initializedDefaultsRef = useRef(false)
  const retryDelayRef = useRef(1_000)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [monitorBaseUrl, setMonitorBaseUrl] = useState(() => getMonitorBaseUrl())
  const [schema, setSchema] = useState<MonitorSchema | null>(null)
  const [showBaseFields, setShowBaseFields] = useState(true)
  const [selectedDomains, setSelectedDomains] = useState<string[]>([])
  const [activeDomainName, setActiveDomainName] = useState<string | null>(null)
  const [activeFilePath, setActiveFilePath] = useState<string | null>(null)
  const [fileData, setFileData] = useState<MonitorFileSource | null>(null)
  const [fileLoading, setFileLoading] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const [selectedSymbolId, setSelectedSymbolId] = useState<string | null>(null)
  const [mermaidSource, setMermaidSource] = useState("classDiagram")
  const [refreshing, setRefreshing] = useState(false)
  const [initializing, setInitializing] = useState(true)
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected")
  const [statusError, setStatusError] = useState<string | null>(null)
  const [sourceData, setSourceData] = useState<MonitorSource | null>(null)
  const [sourceLoading, setSourceLoading] = useState(false)
  const [sourceError, setSourceError] = useState<string | null>(null)
  const [isLeftPanelCollapsed, setIsLeftPanelCollapsed] = useState(false)
  const [isRightPanelCollapsed, setIsRightPanelCollapsed] = useState(false)

  useEffect(() => {
    setMonitorBaseUrl(getMonitorBaseUrl())
  }, [])

  const domainSections = useMemo(() => buildDomainSections(schema), [schema])
  const aliasMap = useMemo(() => buildAliasMap(schema), [schema])
  const filePathToDomainMap = useMemo(() => {
    const nextMap = new Map<string, string>()
    for (const section of domainSections) {
      for (const file of section.files) {
        if (file.path) {
          nextMap.set(file.path, section.name)
        }
      }
    }
    return nextMap
  }, [domainSections])
  const activeDomainSection = useMemo(
    () => domainSections.find((section) => section.name === activeDomainName) ?? null,
    [activeDomainName, domainSections]
  )
  const activeDomainExplorerNodes = useMemo(
    () => buildDomainExplorerNodes(activeDomainSection?.files ?? []),
    [activeDomainSection]
  )
  const activeDomainTreeElements = useMemo(
    () => buildTreeElements(activeDomainExplorerNodes),
    [activeDomainExplorerNodes]
  )
  const activeFileTreeId = useMemo(() => {
    const matchingFile = activeDomainSection?.files.find((file) => file.path === activeFilePath)
    return matchingFile ? `file:${matchingFile.id}` : undefined
  }, [activeDomainSection, activeFilePath])

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

    if (selectedDomains.length === 0) {
      setMermaidSource("classDiagram")
      return
    }

    const params = new URLSearchParams({
      detail_level: "compact",
      domains: selectedDomains.join(","),
      show_base_fields: String(showBaseFields),
    })

    const response = await fetch(buildMonitorUrl(monitorBaseUrl, `api/mermaid?${params.toString()}`), {
      cache: "no-store",
    })
    if (!response.ok) {
      throw new Error("Failed to load Mermaid diagram")
    }

    setMermaidSource(await response.text())
  }, [monitorBaseUrl, schema, selectedDomains, showBaseFields])

  const openFile = useCallback(async (filePath: string) => {
    if (!monitorBaseUrl) {
      return
    }

    setActiveFilePath(filePath)
    setFileLoading(true)
    setFileError(null)

    try {
      const params = new URLSearchParams({ file_path: filePath })
      const response = await fetch(buildMonitorUrl(monitorBaseUrl, `api/file?${params.toString()}`), {
        cache: "no-store",
      })
      if (!response.ok) {
        throw new Error("File lookup failed")
      }

      const payload = (await response.json()) as MonitorFileSource
      startTransition(() => {
        setFileData(payload)
      })
    } catch (error) {
      setFileError(error instanceof Error ? error.message : String(error))
    } finally {
      setFileLoading(false)
    }
  }, [monitorBaseUrl])

  async function openSource(symbolId: string) {
    if (!monitorBaseUrl) {
      return
    }

    setSelectedSymbolId(symbolId)
    setSourceLoading(true)
    setSourceError(null)

    try {
      const response = await fetch(buildMonitorUrl(monitorBaseUrl, `api/source/${symbolId}`), {
        cache: "no-store",
      })
      if (!response.ok) {
        throw new Error("Source lookup failed")
      }

      const payload = (await response.json()) as MonitorSource
      const nextDomainName = filePathToDomainMap.get(payload.file_path)
      startTransition(() => {
        setSourceData(payload)
        if (nextDomainName) {
          setActiveDomainName(nextDomainName)
        }
      })
      await openFile(payload.file_path)
    } catch (error) {
      setSourceError(error instanceof Error ? error.message : String(error))
    } finally {
      setSourceLoading(false)
    }
  }

  const handleFileSelect = useCallback(async (filePath: string) => {
    setSelectedSymbolId(null)
    setSourceData(null)
    setSourceError(null)
    await openFile(filePath)
  }, [openFile])

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

  useEffect(() => {
    if (!activeDomainSection) {
      setActiveFilePath(null)
      setFileData(null)
      return
    }

    const hasActiveFile = activeFilePath
      ? activeDomainSection.files.some((file) => file.path === activeFilePath)
      : false

    if (hasActiveFile) {
      return
    }

    const nextFilePath = activeDomainSection.files.find((file) => file.path)?.path ?? null
    if (!nextFilePath) {
      setActiveFilePath(null)
      setFileData(null)
      return
    }

    setSelectedSymbolId(null)
    setSourceData(null)
    setSourceError(null)
    void openFile(nextFilePath)
  }, [activeDomainSection, activeFilePath, openFile])

  useEffect(() => {
    if (!monitorBaseUrl) {
      return
    }

    let disposed = false

    const connect = () => {
      if (disposed) {
        return
      }

      const socket = new WebSocket(buildMonitorWebSocketUrl(monitorBaseUrl))
      setConnectionState("reconnecting")

      socket.onopen = () => {
        retryDelayRef.current = 1_000
        setConnectionState("connected")
      }

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as {
            defaults?: MonitorSchema["defaults"]
            message?: string
            schema?: MonitorSchema
            type?: "error" | "update"
          }

          if (payload.schema) {
            ingestSchema(payload.schema)
          }

          if (payload.type === "error") {
            setStatusError(payload.message ?? "Monitor update failed")
          } else {
            setStatusError(null)
          }
        } catch {
          /* ignore malformed websocket payloads */
        }
      }

      socket.onerror = () => {
        socket.close()
      }

      socket.onclose = () => {
        setConnectionState("reconnecting")
        reconnectTimerRef.current = setTimeout(connect, retryDelayRef.current)
        retryDelayRef.current = Math.min(retryDelayRef.current * 2, MAX_RETRY_DELAY)
      }

      return socket
    }

    const socket = connect()

    return () => {
      disposed = true
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      socket?.close()
    }
  }, [ingestSchema, monitorBaseUrl])

  async function handleRefresh() {
    setRefreshing(true)
    try {
      setStatusError(null)
      await syncSchema()
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
  const selectedSymbolMeta = sourceData && sourceData.file_path === activeFilePath ? sourceData : null

  const renderExplorerNodes = useCallback((nodes: DomainExplorerNode[], depth = 0): React.ReactNode => {
    return nodes.map((node) => {
      if (node.kind === "directory") {
        return (
          <Folder
            className="w-full rounded-lg px-2 py-1.5 text-sm hover:bg-accent/40"
            element={<span className="truncate">{node.name}</span>}
            key={node.id}
            value={node.id}
          >
            {renderExplorerNodes(node.children ?? [], depth + 1)}
          </Folder>
        )
      }

      return (
        <File
          className={cn(
            "w-full rounded-lg px-2 py-1.5 text-left hover:bg-accent/60",
            depth > 0 && "pl-5"
          )}
          handleSelect={() => {
            if (node.path) {
              void handleFileSelect(node.path)
            }
          }}
          key={node.id}
          value={node.id}
        >
          <span className="truncate font-mono text-[11px]">{node.name}</span>
        </File>
      )
    })
  }, [handleFileSelect])

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
            Toggle visibility with checkboxes, then open any domain label to browse its files on the right.
          </p>
        </div>

        <Separator className="my-4 bg-sidebar-border/70" />

        <div className="flex min-h-0 flex-1 flex-col">
          <div>
            <p className="text-[11px] font-medium tracking-[0.22em] uppercase text-muted-foreground">
              Domains
            </p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Checkboxes filter the diagram. Clicking the label opens that domain in the explorer.
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

        <Separator className="my-4 bg-sidebar-border/70" />

        <div className="space-y-4">
          <div>
            <p className="text-[11px] font-medium tracking-[0.22em] uppercase text-muted-foreground">
              Live status
            </p>
            <div className="mt-2 flex items-center justify-between gap-3">
              <p className="text-sm font-medium">
                {connectionState === "connected"
                  ? "Connected"
                  : connectionState === "reconnecting"
                    ? "Reconnecting"
                    : "Disconnected"}
              </p>
              <span
                className={cn(
                  "size-3 rounded-full",
                  connectionState === "connected" && "bg-emerald-500",
                  connectionState === "reconnecting" && "bg-amber-400",
                  connectionState === "disconnected" && "bg-rose-500"
                )}
              />
            </div>
          </div>
        </div>
      </div>
    </Sidebar>
  )

  const sourcePanel = (
    <Card className="flex h-full flex-col rounded-[28px] border-border/70 bg-card/92 shadow-[0_18px_60px_-42px_rgba(0,0,0,0.7)] backdrop-blur-xl">
      <CardHeader className="border-b border-border/70 px-5 py-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="font-mono text-2xl tracking-[-0.04em]">
              Domain explorer
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Pick a domain on the left, browse its real file tree here, and inspect code in the pane below.
            </p>
          </div>
          {activeDomainSection ? (
            <Badge className="rounded-full border border-border bg-background/80 px-3 py-1.5 text-xs font-medium text-foreground" variant="outline">
              {activeDomainSection.name}
            </Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col p-5">
        {!activeDomainSection ? (
          <div className="flex h-full flex-1 items-center justify-center">
            <div className="max-w-sm rounded-[28px] border bg-background/70 px-6 py-5 text-center">
              <div className="mx-auto mb-3 flex size-10 items-center justify-center rounded-full border bg-muted">
                <CheckCircle2 className="size-4" />
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                Select a domain label from the left sidebar to load its file explorer.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col gap-4">
            <div className="overflow-hidden rounded-[24px] border bg-background/70">
              <div className="border-b border-border/70 px-4 py-3">
                <p className="text-[11px] font-medium tracking-[0.22em] uppercase text-muted-foreground">
                  Explorer
                </p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {activeDomainSection.fileCount} files · {activeDomainSection.classCount} classes · {activeDomainSection.enumCount} enums
                </p>
              </div>
              <div className="h-[260px]">
                <Tree
                  className="h-full"
                  disableIndent
                  elements={activeDomainTreeElements}
                  initialExpandedItems={[]}
                  selectedId={activeFileTreeId}
                >
                  {renderExplorerNodes(activeDomainExplorerNodes)}
                </Tree>
              </div>
            </div>

            <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[24px] border bg-background/70">
              <div className="border-b border-border/70 px-4 py-3">
                {selectedSymbolMeta ? (
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge className="rounded-full bg-primary px-3 py-1 text-[11px] tracking-[0.18em] uppercase text-primary-foreground">
                        {selectedSymbolMeta.kind}
                      </Badge>
                      <Badge className="rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground" variant="outline">
                        lines {selectedSymbolMeta.start_line}-{selectedSymbolMeta.end_line}
                      </Badge>
                    </div>
                    <div>
                      <h3 className="font-mono text-lg tracking-[-0.04em]">{selectedSymbolMeta.name}</h3>
                      <p className="mt-1 break-all text-xs leading-5 text-muted-foreground">
                        {selectedSymbolMeta.file_path}
                      </p>
                    </div>
                  </div>
                ) : fileData ? (
                  <div>
                    <p className="text-[11px] font-medium tracking-[0.22em] uppercase text-muted-foreground">
                      Code
                    </p>
                    <h3 className="mt-2 font-mono text-lg tracking-[-0.04em]">{fileData.name}</h3>
                    <p className="mt-1 break-all text-xs leading-5 text-muted-foreground">
                      {fileData.file_path}
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="text-[11px] font-medium tracking-[0.22em] uppercase text-muted-foreground">
                      Code
                    </p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Select a file to open its contents.
                    </p>
                  </div>
                )}
              </div>

              {fileLoading || sourceLoading ? (
                <div className="space-y-4 p-4">
                  <Skeleton className="h-8 rounded-2xl" />
                  <Skeleton className="h-6 rounded-2xl" />
                  <Skeleton className="h-[380px] rounded-[28px]" />
                </div>
              ) : fileError ? (
                <div className="p-4">
                  <Alert className="rounded-[28px] border-destructive/30 bg-background/70">
                    <ServerCrash className="h-4 w-4" />
                    <AlertTitle>File load failed</AlertTitle>
                    <AlertDescription>{fileError}</AlertDescription>
                  </Alert>
                </div>
              ) : sourceError ? (
                <div className="p-4">
                  <Alert className="rounded-[28px] border-destructive/30 bg-background/70">
                    <ServerCrash className="h-4 w-4" />
                    <AlertTitle>Source lookup failed</AlertTitle>
                    <AlertDescription>{sourceError}</AlertDescription>
                  </Alert>
                </div>
              ) : fileData ? (
                <ScrollArea className="min-h-0 flex-1">
                  <pre className="min-h-full p-5 font-mono text-[12px] leading-6 text-foreground">
                    {fileData.content}
                  </pre>
                </ScrollArea>
              ) : (
                <div className="flex h-full flex-1 items-center justify-center px-6">
                  <p className="text-sm leading-6 text-muted-foreground">
                    Choose a file from the tree or click a diagram node to load code here.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
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
      onSymbolSelect={(symbolId) => {
        void openSource(symbolId)
      }}
      selectedSymbolId={selectedSymbolId}
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
                    Monitor schema changes in real time, pivot domains instantly, and inspect the exact source that produced each Mermaid node.
                  </p>
                </div>
                <ThemeModeControl />
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
              <div className="min-h-[34vh]">{sourcePanel}</div>
            </div>
          </div>
        </div>
      </SidebarProvider>
    )
  }

  return (
    <SidebarProvider>
      <div className="relative h-screen w-screen overflow-hidden bg-background text-foreground">
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
                  Full-screen schema canvas with live FastAPI updates and source inspection.
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
        <div
          className={cn(
            "absolute bottom-4 right-4 z-30 transition-[width] duration-300 ease-out",
            desktopPanelTopOffset,
            isRightPanelCollapsed ? "w-14" : "w-[360px]"
          )}
        >
          {isRightPanelCollapsed ? (
            <Card className="flex h-full flex-col items-center justify-between rounded-[24px] border-border/70 bg-card/88 py-4 shadow-[0_18px_60px_-42px_rgba(0,0,0,0.7)] backdrop-blur-xl">
              <Button
                aria-label="Expand right panel"
                className="size-9 rounded-full"
                onClick={() => setIsRightPanelCollapsed(false)}
                size="icon"
                type="button"
                variant="outline"
              >
                <ChevronLeft className="size-4" />
              </Button>
              <div className="[writing-mode:vertical-rl] rotate-180 text-[10px] font-medium tracking-[0.28em] uppercase text-muted-foreground">
                Source
              </div>
              <Badge className="rounded-full border border-border bg-background/80 px-2 py-1 text-[10px]" variant="outline">
                {selectedSymbolId ? "1" : "0"}
              </Badge>
            </Card>
          ) : (
            <div className="relative h-full">
              <div className="absolute left-0 top-4 z-10 -translate-x-1/2">
                <Button
                  aria-label="Collapse right panel"
                  className="size-9 rounded-full shadow-sm"
                  onClick={() => setIsRightPanelCollapsed(true)}
                  size="icon"
                  type="button"
                  variant="outline"
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
              {sourcePanel}
            </div>
          )}
        </div>
      </div>
    </SidebarProvider>
  )
}
