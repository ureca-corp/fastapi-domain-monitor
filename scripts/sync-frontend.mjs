import { cp, mkdir, rm } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, "..")
const sourceDir = path.join(repoRoot, "frontend", "out")
const targetDir = path.join(repoRoot, "src", "fastapi_domain_monitor", "static", "dashboard")

async function main() {
  await rm(targetDir, { recursive: true, force: true })
  await mkdir(targetDir, { recursive: true })
  await cp(sourceDir, targetDir, { recursive: true })
  console.log(`Synced frontend export from ${sourceDir} to ${targetDir}`)
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
