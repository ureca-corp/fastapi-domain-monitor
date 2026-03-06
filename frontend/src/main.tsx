import "@fontsource-variable/inter"
import "@fontsource-variable/jetbrains-mono"

import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "@/app/globals.css"

import App from "./App"

const rootElement = document.getElementById("root")

if (!rootElement) {
  throw new Error("Root element #root was not found.")
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
)
