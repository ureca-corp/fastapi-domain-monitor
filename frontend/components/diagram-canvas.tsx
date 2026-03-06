"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Expand, Minus, Move, Plus, SearchX } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

declare global {
  interface Window {
    handleSymbolClick?: (mermaidId?: string) => void
  }
}

type DiagramCanvasProps = {
  aliasMap: Map<string, string>
  className?: string
  onSymbolSelect: (symbolId: string) => void
  selectedSymbolId: string | null
  source: string
  theme: "light" | "dark"
}

type TransformState = {
  hasUserViewportOverride: boolean
  panX: number
  panY: number
  scale: number
}

const INITIAL_TRANSFORM: TransformState = {
  hasUserViewportOverride: false,
  panX: 0,
  panY: 0,
  scale: 1,
}

const MERMAID_MAX_TEXT_SIZE = 200_000
const MERMAID_MAX_EDGES = 2_000

export function DiagramCanvas({
  aliasMap,
  className,
  onSymbolSelect,
  selectedSymbolId,
  source,
  theme,
}: DiagramCanvasProps) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const renderCounterRef = useRef(0)
  const transformRef = useRef<TransformState>({ ...INITIAL_TRANSFORM })
  const panStateRef = useRef({
    active: false,
    startX: 0,
    startY: 0,
  })
  const [statusMessage, setStatusMessage] = useState<string | null>("Loading diagram…")
  const [renderError, setRenderError] = useState<string | null>(null)
  const [zoomPercent, setZoomPercent] = useState(100)

  const applyTransform = useCallback(() => {
    const container = containerRef.current
    if (!container) {
      return
    }

    const { panX, panY, scale } = transformRef.current
    container.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`
    setZoomPercent(Math.round(scale * 100))
  }, [])

  const resetTransform = useCallback(() => {
    transformRef.current = { ...INITIAL_TRANSFORM }

    const container = containerRef.current
    if (!container) {
      return
    }

    container.style.transform = "none"
    setZoomPercent(100)
  }, [])

  const getSvgIntrinsicSize = useCallback((svgElement: SVGSVGElement) => {
    const viewBox = svgElement.viewBox?.baseVal
    if (viewBox && viewBox.width > 0 && viewBox.height > 0) {
      return {
        height: viewBox.height,
        width: viewBox.width,
      }
    }

    const width = Number.parseFloat(svgElement.getAttribute("width") ?? "")
    const height = Number.parseFloat(svgElement.getAttribute("height") ?? "")
    if (Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0) {
      return { height, width }
    }

    const box = svgElement.getBBox()
    return {
      height: box.height,
      width: box.width,
    }
  }, [])

  const fitDiagramToViewport = useCallback(() => {
    const wrapper = wrapperRef.current
    const container = containerRef.current
    const svgElement = container?.querySelector("svg")

    if (!wrapper || !container || !(svgElement instanceof SVGSVGElement)) {
      resetTransform()
      return
    }

    const wrapperRect = wrapper.getBoundingClientRect()
    const { height, width } = getSvgIntrinsicSize(svgElement)

    if (!(wrapperRect.width > 0 && wrapperRect.height > 0 && width > 0 && height > 0)) {
      resetTransform()
      svgElement.style.width = ""
      svgElement.style.height = ""
      return
    }

    const padding = 40
    const availableWidth = Math.max(wrapperRect.width - padding * 2, 1)
    const availableHeight = Math.max(wrapperRect.height - padding * 2, 1)
    const fitScale = Math.min(1, availableWidth / width, availableHeight / height)

    svgElement.style.width = `${Math.max(width * fitScale, 1)}px`
    svgElement.style.height = `${Math.max(height * fitScale, 1)}px`
    resetTransform()
  }, [getSvgIntrinsicSize, resetTransform])

  const syncSelectedNodeHighlight = useCallback(() => {
    const container = containerRef.current
    if (!container) {
      return
    }

    for (const node of container.querySelectorAll<SVGGElement>(".selected-node")) {
      node.classList.remove("selected-node")
    }

    if (!selectedSymbolId) {
      return
    }

    const selectedNode = container.querySelector<SVGGElement>(`[id="node_${selectedSymbolId}"]`)
    selectedNode?.classList.add("selected-node")
  }, [selectedSymbolId])

  const clearContainer = useCallback(() => {
    const container = containerRef.current
    if (!container) {
      return
    }

    while (container.firstChild) {
      container.removeChild(container.firstChild)
    }
  }, [])

  useEffect(() => {
    const handler = (mermaidId?: string) => {
      const symbolId = aliasMap.get(mermaidId ?? "") ?? selectedSymbolId
      if (symbolId) {
        onSymbolSelect(symbolId)
      }
    }

    window.handleSymbolClick = handler

    return () => {
      if (window.handleSymbolClick === handler) {
        delete window.handleSymbolClick
      }
    }
  }, [aliasMap, onSymbolSelect, selectedSymbolId])

  useEffect(() => {
    let cancelled = false

    async function renderDiagram() {
      if (source.trim() === "classDiagram") {
        clearContainer()
        setRenderError(null)
        setStatusMessage("No visible domains")
        return
      }

      setRenderError(null)
      setStatusMessage(null)

      try {
        const mermaidModule = await import("mermaid")
        const mermaid = mermaidModule.default
        mermaid.initialize({
          maxEdges: MERMAID_MAX_EDGES,
          maxTextSize: MERMAID_MAX_TEXT_SIZE,
          startOnLoad: false,
          securityLevel: "loose",
          theme: theme === "dark" ? "dark" : "base",
          class: {
            hideEmptyMembersBox: true,
          },
        })

        renderCounterRef.current += 1
        const renderId = `domain-monitor-diagram-${renderCounterRef.current}`
        const { bindFunctions, svg } = await mermaid.render(renderId, source)

        if (cancelled) {
          return
        }

        const documentNode = new DOMParser().parseFromString(svg, "image/svg+xml")
        const svgElement = documentNode.documentElement
        if (svgElement.nodeName !== "svg") {
          throw new Error("Mermaid did not return an SVG element.")
        }

        clearContainer()
        const adoptedSvg = document.adoptNode(svgElement) as unknown as SVGSVGElement
        adoptedSvg.classList.add("h-auto", "w-auto")

        const container = containerRef.current
        if (!container) {
          return
        }

        container.appendChild(adoptedSvg)
        bindFunctions?.(container)

        if (!transformRef.current.hasUserViewportOverride) {
          fitDiagramToViewport()
        }
        syncSelectedNodeHighlight()
      } catch (error) {
        if (cancelled) {
          return
        }

        clearContainer()
        setRenderError(error instanceof Error ? error.message : String(error))
      }
    }

    void renderDiagram()

    return () => {
      cancelled = true
    }
  }, [clearContainer, fitDiagramToViewport, source, syncSelectedNodeHighlight, theme])

  useEffect(() => {
    syncSelectedNodeHighlight()
  }, [syncSelectedNodeHighlight])

  useEffect(() => {
    const handleResize = () => {
      if (!transformRef.current.hasUserViewportOverride) {
        fitDiagramToViewport()
      }
    }

    window.addEventListener("resize", handleResize)
    return () => window.removeEventListener("resize", handleResize)
  }, [fitDiagramToViewport])

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!panStateRef.current.active) {
        return
      }

      transformRef.current.panX = event.clientX - panStateRef.current.startX
      transformRef.current.panY = event.clientY - panStateRef.current.startY
      applyTransform()
    }

    const handleMouseUp = () => {
      panStateRef.current.active = false
    }

    window.addEventListener("mousemove", handleMouseMove)
    window.addEventListener("mouseup", handleMouseUp)

    return () => {
      window.removeEventListener("mousemove", handleMouseMove)
      window.removeEventListener("mouseup", handleMouseUp)
    }
  }, [applyTransform])

  const diagramSummaryIcon = useMemo(
    () =>
      renderError ? (
        <SearchX className="size-4" />
      ) : (
        <Move className="size-4" />
      ),
    [renderError]
  )

  const zoomBy = useCallback(
    (delta: number) => {
      const wrapper = wrapperRef.current
      if (!wrapper) {
        return
      }

      const rect = wrapper.getBoundingClientRect()
      const centerX = rect.width / 2
      const centerY = rect.height / 2
      const nextScale = Math.max(0.12, transformRef.current.scale * delta)
      const ratio = nextScale / transformRef.current.scale

      transformRef.current.hasUserViewportOverride = true
      transformRef.current.panX = centerX - ratio * (centerX - transformRef.current.panX)
      transformRef.current.panY = centerY - ratio * (centerY - transformRef.current.panY)
      transformRef.current.scale = nextScale

      applyTransform()
    },
    [applyTransform]
  )

  return (
    <div className={cn("relative h-full min-h-[360px] overflow-hidden rounded-[28px] border bg-background/80", className)}>
      <div
        className="relative h-full w-full cursor-grab overflow-hidden active:cursor-grabbing"
        onDoubleClick={fitDiagramToViewport}
        onMouseDown={(event) => {
          if (event.button !== 0) {
            return
          }

          panStateRef.current.active = true
          transformRef.current.hasUserViewportOverride = true
          panStateRef.current.startX = event.clientX - transformRef.current.panX
          panStateRef.current.startY = event.clientY - transformRef.current.panY
        }}
        onWheel={(event) => {
          event.preventDefault()

          const wrapper = wrapperRef.current
          if (!wrapper) {
            return
          }

          const rect = wrapper.getBoundingClientRect()
          const mouseX = event.clientX - rect.left
          const mouseY = event.clientY - rect.top
          const delta = event.deltaY > 0 ? 0.9 : 1.1
          const nextScale = Math.max(0.12, transformRef.current.scale * delta)
          const ratio = nextScale / transformRef.current.scale

          transformRef.current.hasUserViewportOverride = true
          transformRef.current.panX = mouseX - ratio * (mouseX - transformRef.current.panX)
          transformRef.current.panY = mouseY - ratio * (mouseY - transformRef.current.panY)
          transformRef.current.scale = nextScale

          applyTransform()
        }}
        ref={wrapperRef}
      >
        <div
          className="flex h-full w-full items-center justify-center p-6 [transform-origin:0_0]"
          ref={containerRef}
        />

        {(statusMessage || renderError) && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-6">
            <div className="max-w-md rounded-[28px] border bg-card/95 px-6 py-5 text-center shadow-xl backdrop-blur">
              <div className="mx-auto mb-3 flex size-10 items-center justify-center rounded-full border bg-muted">
                {diagramSummaryIcon}
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                {renderError ?? statusMessage}
              </p>
            </div>
          </div>
        )}

        <div className="absolute bottom-4 left-1/2 z-20 -translate-x-1/2">
          <div className="flex items-center gap-1 rounded-full border border-border/70 bg-card/88 px-2 py-2 shadow-[0_18px_60px_-42px_rgba(0,0,0,0.7)] backdrop-blur-xl">
            <Button
              className="size-8 rounded-full"
              onClick={() => zoomBy(0.9)}
              size="icon"
              type="button"
              variant="outline"
            >
              <Minus className="size-3.5" />
            </Button>
            <div className="min-w-14 text-center font-mono text-xs tracking-[0.16em] uppercase text-foreground">
              {zoomPercent}%
            </div>
            <Button
              className="size-8 rounded-full"
              onClick={() => zoomBy(1.1)}
              size="icon"
              type="button"
              variant="outline"
            >
              <Plus className="size-3.5" />
            </Button>
            <div className="mx-1 h-5 w-px bg-border/70" />
            <Button
              className="h-8 rounded-full px-3 text-[10px] tracking-[0.2em] uppercase"
              onClick={fitDiagramToViewport}
              type="button"
              variant="outline"
            >
              <Expand className="mr-1 size-3.5" />
              Fit
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
