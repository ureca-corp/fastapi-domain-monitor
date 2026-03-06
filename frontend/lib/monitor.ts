export type MonitorDetailLevel = "compact"
export type ConnectionState = "connected" | "disconnected" | "reconnecting"

export type MonitorDefaults = {
  detail_level?: MonitorDetailLevel
  show_base_fields?: boolean
  watch_patterns?: string[]
}

export type MonitorModuleEntry = {
  symbol_id: string
  name: string
}

export type MonitorClassEntry = MonitorModuleEntry & {
  stereotypes?: string[]
}

export type MonitorModule = {
  domain_name: string
  file_path?: string
  classes?: MonitorClassEntry[]
  enums?: MonitorModuleEntry[]
}

export type MonitorDomainFileEntry = MonitorModuleEntry & {
  kind: "class" | "enum"
}

export type MonitorDomainFile = {
  id: string
  label: string
  path: string | null
  relativePath: string
  classCount: number
  enumCount: number
  entries: MonitorDomainFileEntry[]
}

export type MonitorDomainSection = {
  name: string
  fileCount: number
  classCount: number
  enumCount: number
  files: MonitorDomainFile[]
}

export type MonitorSchema = {
  generated_at?: string | null
  modules?: MonitorModule[]
  defaults?: MonitorDefaults
}

export type MonitorSource = {
  symbol_id: string
  name: string
  kind: "class" | "enum"
  file_path: string
  start_line: number
  end_line: number
  excerpt: string
}

export type MonitorFileSource = {
  file_path: string
  name: string
  content: string
  line_count: number
}

export type MonitorSocketMessage = {
  type: "update" | "error"
  message?: string
  schema?: MonitorSchema
  defaults?: MonitorDefaults
  mermaid?: string
}

export function getMonitorBaseUrl() {
  const configuredBase = import.meta.env.VITE_MONITOR_BASE_URL?.trim()
  if (configuredBase) {
    return configuredBase.replace(/\/$/, "")
  }

  if (typeof window === "undefined") {
    return import.meta.env.DEV ? "/domain-monitor" : ""
  }

  const derivedBase = window.location.pathname.replace(/\/$/, "")
  if (derivedBase) {
    return derivedBase
  }

  return import.meta.env.DEV ? "/domain-monitor" : ""
}

export function buildMonitorUrl(baseUrl: string, relativePath: string) {
  const cleanPath = relativePath.replace(/^\//, "")

  if (/^https?:\/\//.test(baseUrl)) {
    const normalizedBase = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`
    return new URL(cleanPath, normalizedBase).toString()
  }

  const normalizedBase = baseUrl.replace(/\/$/, "")
  return `${normalizedBase}/${cleanPath}`
}

export function buildMonitorWebSocketUrl(baseUrl: string) {
  if (/^https?:\/\//.test(baseUrl)) {
    const target = new URL(baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`)
    target.protocol = target.protocol === "https:" ? "wss:" : "ws:"
    target.pathname = `${target.pathname.replace(/\/$/, "")}/ws`
    return target.toString()
  }

  const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${wsProtocol}//${window.location.host}${baseUrl.replace(/\/$/, "")}/ws`
}

export function summarizeSchema(schema: MonitorSchema | null) {
  if (!schema?.modules?.length) {
    return {
      totalDomains: 0,
      totalClasses: 0,
      totalEnums: 0,
    }
  }

  return schema.modules.reduce(
    (summary, schemaModule) => ({
      totalDomains: summary.totalDomains + 1,
      totalClasses: summary.totalClasses + (schemaModule.classes?.length ?? 0),
      totalEnums: summary.totalEnums + (schemaModule.enums?.length ?? 0),
    }),
    {
      totalDomains: 0,
      totalClasses: 0,
      totalEnums: 0,
    }
  )
}

export function getAvailableDomains(schema: MonitorSchema | null) {
  return [...new Set((schema?.modules ?? []).map((module) => module.domain_name))].sort(
    (left, right) => left.localeCompare(right)
  )
}

function normalizePath(filePath: string) {
  return filePath.replaceAll("\\", "/")
}

function formatDomainFileLabel(domain: string, filePath?: string) {
  if (!filePath) {
    return "unknown.py"
  }

  const normalizedPath = normalizePath(filePath)
  const modulesMarker = `/modules/${domain}/`
  if (normalizedPath.includes(modulesMarker)) {
    return normalizedPath.split(modulesMarker)[1] || normalizedPath.split("/").at(-1) || filePath
  }

  const domainMarker = `/${domain}/`
  if (normalizedPath.includes(domainMarker)) {
    return normalizedPath.split(domainMarker)[1] || normalizedPath.split("/").at(-1) || filePath
  }

  return normalizedPath.split("/").at(-1) || filePath
}

export function buildDomainSections(schema: MonitorSchema | null): MonitorDomainSection[] {
  if (!schema?.modules?.length) {
    return []
  }

  const grouped = new Map<string, MonitorDomainSection>()

  for (const schemaModule of schema.modules) {
    const currentSection = grouped.get(schemaModule.domain_name) ?? {
      name: schemaModule.domain_name,
      fileCount: 0,
      classCount: 0,
      enumCount: 0,
      files: [],
    }

    const classEntries = (schemaModule.classes ?? []).map((item) => ({ ...item, kind: "class" as const }))
    const enumEntries = (schemaModule.enums ?? []).map((item) => ({ ...item, kind: "enum" as const }))
    const entries = [...classEntries, ...enumEntries].sort((left, right) => {
      if (left.kind !== right.kind) {
        return left.kind.localeCompare(right.kind)
      }
      return left.name.localeCompare(right.name)
    })

    currentSection.files.push({
      id: schemaModule.file_path ?? `${schemaModule.domain_name}-${currentSection.files.length}`,
      label: formatDomainFileLabel(schemaModule.domain_name, schemaModule.file_path),
      path: schemaModule.file_path ?? null,
      relativePath: formatDomainFileLabel(schemaModule.domain_name, schemaModule.file_path),
      classCount: classEntries.length,
      enumCount: enumEntries.length,
      entries,
    })
    currentSection.fileCount += 1
    currentSection.classCount += classEntries.length
    currentSection.enumCount += enumEntries.length

    grouped.set(schemaModule.domain_name, currentSection)
  }

  return [...grouped.values()]
    .map((section) => ({
      ...section,
      files: [...section.files].sort((left, right) => left.label.localeCompare(right.label)),
    }))
    .sort((left, right) => left.name.localeCompare(right.name))
}

export function buildAvailableStereotypes(schema: MonitorSchema | null): string[] {
  const types = new Set<string>()
  for (const module of schema?.modules ?? []) {
    for (const cls of module.classes ?? []) {
      if (cls.stereotypes?.length) {
        for (const s of cls.stereotypes) types.add(s)
      } else {
        types.add("Other")
      }
    }
    if ((module.enums?.length ?? 0) > 0) {
      types.add("Enumeration")
    }
  }
  return [...types].sort()
}

export function buildAliasMap(schema: MonitorSchema | null) {
  const aliasMap = new Map<string, string>()

  for (const schemaModule of schema?.modules ?? []) {
    for (const item of [...(schemaModule.classes ?? []), ...(schemaModule.enums ?? [])]) {
      aliasMap.set(`node_${item.symbol_id}`, item.symbol_id)
    }
  }

  return aliasMap
}
