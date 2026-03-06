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

type MermaidPalette = {
  border: string
  borderSoft: string
  canvas: string
  line: string
  note: string
  shadow: string
  surface: string
  surfaceMuted: string
  text: string
  textMuted: string
}

const INITIAL_TRANSFORM: TransformState = {
  hasUserViewportOverride: false,
  panX: 0,
  panY: 0,
  scale: 1,
}

const MERMAID_MAX_TEXT_SIZE = 200_000
const MERMAID_MAX_EDGES = 2_000
const MERMAID_FONT_STACK =
  '"Inter Variable", "SF Pro Display", ui-sans-serif, system-ui, sans-serif'
const MERMAID_MONO_STACK =
  '"JetBrains Mono Variable", "SFMono-Regular", ui-monospace, monospace'
const MERMAID_FIELD_VISIBILITY_PREFIXES = new Set(["+", "-", "#", "~"])

type MermaidFieldParts = {
  defaultLine: string | null
  name: string
  signature: string
}

function isClassDiagramSource(source: string) {
  return source.trimStart().startsWith("classDiagram")
}

function getMermaidPalette(theme: "light" | "dark"): MermaidPalette {
  if (theme === "dark") {
    return {
      border: "rgba(255, 255, 255, 0.18)",
      borderSoft: "rgba(255, 255, 255, 0.10)",
      canvas: "#09090b",
      line: "rgba(228, 228, 231, 0.42)",
      note: "#18181b",
      shadow: "rgba(0, 0, 0, 0.40)",
      surface: "rgba(26, 26, 34, 0.90)",
      surfaceMuted: "rgba(20, 20, 28, 0.88)",
      text: "#fafafa",
      textMuted: "#a1a1aa",
    }
  }

  return {
    border: "rgba(15, 15, 18, 0.16)",
    borderSoft: "rgba(15, 15, 18, 0.09)",
    canvas: "#f8f8fa",
    line: "rgba(25, 25, 30, 0.38)",
    note: "#f4f4f5",
    shadow: "rgba(0, 0, 0, 0.08)",
    surface: "#ffffff",
    surfaceMuted: "rgba(246, 246, 251, 0.95)",
    text: "#18181b",
    textMuted: "#71717a",
  }
}

function getClassDiagramTheme(theme: "light" | "dark") {
  const palette = getMermaidPalette(theme)

  return {
    theme: "base" as const,
    themeCSS: `
      svg {
        background: transparent;
      }

      .node rect,
      .node circle,
      .node ellipse,
      .node polygon,
      .node path,
      g.classGroup rect,
      .edgeLabel .label rect,
      .classLabel .box {
        rx: 28px;
        ry: 28px;
      }

      .node rect,
      .node circle,
      .node ellipse,
      .node polygon,
      .node path {
        fill: ${palette.surface};
        stroke: ${palette.border};
        stroke-width: 1.2px;
      }

      g.node.default {
        filter: drop-shadow(0 2px 6px ${palette.shadow});
      }

      g.cluster rect {
        fill: transparent;
        stroke: ${palette.borderSoft};
        stroke-width: 1px;
        rx: 16px;
        ry: 16px;
      }

      g.cluster-label span,
      g.cluster-label text {
        color: ${palette.textMuted};
        fill: ${palette.textMuted};
        font-family: ${MERMAID_FONT_STACK};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
      }

      g.classGroup rect {
        fill: ${palette.surfaceMuted};
        stroke: ${palette.borderSoft};
        stroke-width: 1px;
      }

      g.classGroup line,
      .divider,
      .relation {
        stroke: ${palette.line};
        stroke-width: 1.1px;
      }

      g.classGroup text,
      .nodeLabel,
      .edgeLabel,
      .edgeLabel span,
      .label text,
      .edgeTerminals {
        color: ${palette.text};
        fill: ${palette.text};
        font-family: ${MERMAID_MONO_STACK};
        font-size: 11px;
      }

      .classTitleText,
      .classTitle {
        fill: ${palette.text};
        color: ${palette.text};
        font-family: ${MERMAID_FONT_STACK};
        font-size: 16px;
        font-weight: 600;
        letter-spacing: -0.02em;
      }

      .classLabel .box {
        fill: ${palette.canvas};
        stroke: none;
        opacity: 0.94;
      }

      .classLabel .label {
        fill: ${palette.textMuted};
        color: ${palette.textMuted};
        font-family: ${MERMAID_MONO_STACK};
        font-size: 10px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }

      .edgeLabel .label rect,
      .labelBkg {
        fill: ${palette.canvas};
        stroke: ${palette.borderSoft};
        stroke-width: 1px;
      }

      .edgeLabel .label span {
        background: ${palette.canvas};
        border: 1px solid ${palette.borderSoft};
        border-radius: 999px;
        color: ${palette.text};
        display: inline-block;
        padding: 0.18rem 0.55rem;
      }

      .dashed-line {
        stroke-dasharray: 5 4;
      }

      .dotted-line {
        stroke-dasharray: 1.5 4;
      }

      #compositionStart,
      #compositionEnd,
      .composition,
      #dependencyStart,
      #dependencyEnd,
      .dependency {
        fill: ${palette.line} !important;
        stroke: ${palette.line} !important;
      }

      #extensionStart,
      #extensionEnd,
      .extension,
      #aggregationStart,
      #aggregationEnd,
      .aggregation {
        fill: ${palette.canvas} !important;
        stroke: ${palette.line} !important;
      }

      #lollipopStart,
      #lollipopEnd,
      .lollipop {
        fill: ${palette.surface} !important;
        stroke: ${palette.line} !important;
      }
    `,
    themeVariables: {
      background: palette.canvas,
      classText: palette.text,
      clusterBkg: palette.surfaceMuted,
      clusterBorder: palette.borderSoft,
      edgeLabelBackground: palette.canvas,
      fontFamily: MERMAID_MONO_STACK,
      lineColor: palette.line,
      mainBkg: palette.surface,
      nodeBorder: palette.border,
      noteBkgColor: palette.note,
      noteBorderColor: palette.borderSoft,
      primaryBorderColor: palette.border,
      primaryColor: palette.surface,
      primaryTextColor: palette.text,
      secondaryColor: palette.surfaceMuted,
      secondaryTextColor: palette.text,
      tertiaryColor: palette.note,
      tertiaryTextColor: palette.text,
      textColor: palette.text,
    },
  }
}

function roundSvgRects(
  svgElement: SVGSVGElement,
  selector: string,
  { radius, radiusY = radius }: { radius: string; radiusY?: string }
) {
  for (const node of svgElement.querySelectorAll<SVGRectElement>(selector)) {
    node.setAttribute("rx", radius)
    node.setAttribute("ry", radiusY)
  }
}

function parseMermaidFieldLabel(text: string): MermaidFieldParts | null {
  const collapsed = text.replace(/\s+/g, " ").trim()
  if (!collapsed || !MERMAID_FIELD_VISIBILITY_PREFIXES.has(collapsed.charAt(0))) {
    return null
  }

  const match = /^([+#~-].*\s)([A-Za-z_][A-Za-z0-9_]*)(?:\s*=\s*(.+))?$/.exec(collapsed)
  if (!match) {
    return null
  }

  const signature = match[1].trimEnd()
  if (signature.endsWith(")")) {
    return null
  }

  return {
    defaultLine: match[3] ? `default ${match[3].trim()}` : null,
    name: match[2],
    signature,
  }
}

function createMemberLine(label: string, documentNode: Document, className: string) {
  const line = documentNode.createElement("span")
  line.className = className
  line.textContent = label
  return line
}

function decorateClassDiagramFieldLabels(svgElement: SVGSVGElement) {
  for (const label of svgElement.querySelectorAll<SVGGElement>(".members-group .label")) {
    const foreignObject = label.querySelector("foreignObject")
    const contentWrapper = foreignObject?.querySelector("div")
    const content = contentWrapper?.querySelector("span.nodeLabel")

    if (!(foreignObject instanceof SVGForeignObjectElement)) {
      continue
    }
    if (!(contentWrapper instanceof HTMLElement) || !(content instanceof HTMLElement)) {
      continue
    }

    const field = parseMermaidFieldLabel(content.textContent ?? "")
    if (!field) {
      continue
    }

    content.classList.add("mermaid-member-stack")
    content.replaceChildren(
      createMemberLine(field.signature, document, "mermaid-member-type"),
      createMemberLine(field.name, document, "mermaid-member-name"),
      ...(field.defaultLine
        ? [createMemberLine(field.defaultLine, document, "mermaid-member-default")]
        : [])
    )

    contentWrapper.style.display = "flex"
    contentWrapper.style.alignItems = "center"
    contentWrapper.style.height = "100%"
    contentWrapper.style.maxWidth = "none"
    contentWrapper.style.textAlign = "left"
    contentWrapper.style.whiteSpace = "normal"
  }
}

function roundedRectD(xMin: number, yMin: number, xMax: number, yMax: number, r: number): string {
  const rx = Math.min(r, (xMax - xMin) / 2)
  const ry = Math.min(r, (yMax - yMin) / 2)
  return (
    `M ${xMin + rx},${yMin} L ${xMax - rx},${yMin} Q ${xMax},${yMin} ${xMax},${yMin + ry} ` +
    `L ${xMax},${yMax - ry} Q ${xMax},${yMax} ${xMax - rx},${yMax} ` +
    `L ${xMin + rx},${yMax} Q ${xMin},${yMax} ${xMin},${yMax - ry} ` +
    `L ${xMin},${yMin + ry} Q ${xMin},${yMin} ${xMin + rx},${yMin} Z`
  )
}

function roundClassNodes(svgElement: SVGSVGElement, radius: number) {
  let defs = svgElement.querySelector("defs")
  if (!defs) {
    defs = document.createElementNS("http://www.w3.org/2000/svg", "defs")
    svgElement.prepend(defs)
  }

  let idx = 0
  // g.node 하위의 컨테이너만 처리 — namespace cluster 라벨(g.cluster 하위)은 제외
  for (const container of svgElement.querySelectorAll<SVGGElement>("g.node g.basic.label-container")) {
    const fillPath = container.querySelector<SVGPathElement>('path[stroke="none"]')
    if (!fillPath) continue

    let xMin = Infinity, yMin = Infinity, xMax = -Infinity, yMax = -Infinity
    for (const m of (fillPath.getAttribute("d") ?? "").matchAll(/[ML]\s*([-\d.]+)\s+([-\d.]+)/g)) {
      const x = parseFloat(m[1]), y = parseFloat(m[2])
      if (x < xMin) xMin = x
      if (y < yMin) yMin = y
      if (x > xMax) xMax = x
      if (y > yMax) yMax = y
    }
    if (!isFinite(xMin)) continue

    const newD = roundedRectD(xMin, yMin, xMax, yMax, radius)
    // fill path와 border path 모두 같은 둥근 사각형으로 교체
    for (const p of container.querySelectorAll<SVGPathElement>("path")) {
      p.setAttribute("d", newD)
    }

    const clipId = `node-clip-${idx++}`
    const clipPath = document.createElementNS("http://www.w3.org/2000/svg", "clipPath")
    clipPath.id = clipId
    const cr = document.createElementNS("http://www.w3.org/2000/svg", "rect")
    cr.setAttribute("x", String(xMin))
    cr.setAttribute("y", String(yMin))
    cr.setAttribute("width", String(xMax - xMin))
    cr.setAttribute("height", String(yMax - yMin))
    cr.setAttribute("rx", String(radius))
    cr.setAttribute("ry", String(radius))
    clipPath.appendChild(cr)
    defs.appendChild(clipPath)
    container.setAttribute("clip-path", `url(#${clipId})`)
  }
}

function decorateClassDiagramSvg(svgElement: SVGSVGElement) {
  roundClassNodes(svgElement, 28)
  roundSvgRects(svgElement, ".edgeLabel .label rect", {
    radius: "999",
    radiusY: "999",
  })
  decorateClassDiagramFieldLabels(svgElement)
}

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
  const zoomLabelRef = useRef<HTMLDivElement>(null)
  const zoomPercentRef = useRef(100)
  const [statusMessage, setStatusMessage] = useState<string | null>("Loading diagram…")
  const [renderError, setRenderError] = useState<string | null>(null)

  const syncZoomLabel = useCallback((nextZoomPercent: number) => {
    if (zoomPercentRef.current === nextZoomPercent) {
      return
    }

    zoomPercentRef.current = nextZoomPercent
    if (zoomLabelRef.current) {
      zoomLabelRef.current.textContent = `${nextZoomPercent}%`
    }
  }, [])

  const applyTransform = useCallback(() => {
    const container = containerRef.current
    if (!container) {
      return
    }

    const { panX, panY, scale } = transformRef.current
    container.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`
    syncZoomLabel(Math.round(scale * 100))
  }, [syncZoomLabel])

  const resetTransform = useCallback(() => {
    transformRef.current = { ...INITIAL_TRANSFORM }

    const container = containerRef.current
    if (!container) {
      return
    }

    container.style.transform = "none"
    syncZoomLabel(100)
  }, [syncZoomLabel])

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
        const isClassDiagram = isClassDiagramSource(source)

        mermaid.initialize({
          maxEdges: MERMAID_MAX_EDGES,
          maxTextSize: MERMAID_MAX_TEXT_SIZE,
          startOnLoad: false,
          securityLevel: "loose",
          theme: theme === "dark" ? "dark" : "base",
          class: {
            hideEmptyMembersBox: true,
          },
          ...(isClassDiagram ? getClassDiagramTheme(theme) : {}),
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
        adoptedSvg.classList.add("h-auto", "w-auto", "mermaid-diagram")
        if (isClassDiagram) {
          decorateClassDiagramSvg(adoptedSvg)
          adoptedSvg.classList.add("mermaid-class-diagram")
          adoptedSvg.dataset.diagramType = "class"
        }

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
    <div
      className={cn(
        "mermaid-shell relative h-full min-h-[360px] overflow-hidden rounded-[28px] border bg-background/80",
        className
      )}
    >
      <div
        className="mermaid-wrapper relative h-full w-full cursor-grab overflow-hidden active:cursor-grabbing"
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
            <div
              className="min-w-14 text-center font-mono text-xs tracking-[0.16em] uppercase text-foreground"
              ref={zoomLabelRef}
            >
              100%
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
