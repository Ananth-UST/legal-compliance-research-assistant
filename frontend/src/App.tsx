import { useState, useEffect } from "react"
import "./App.css"
import Auth from "./components/Auth"
import Dashboard from "./components/Dashboard"

import { PreferencesProvider } from "./contexts/PreferencesContext"

import { ErrorBoundary } from "./components/ErrorBoundary"

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(() => !!localStorage.getItem("access_token"))
  const [showCookieBanner, setShowCookieBanner] = useState(false)
  const [showCookieModal, setShowCookieModal] = useState(false)

  useEffect(() => {
    if (!localStorage.getItem("opuslex_cookie_consent")) {
      setShowCookieBanner(true)
    }

    const handleOpenSettings = () => {
      setShowCookieModal(true)
      setShowCookieBanner(false)
    }
    
    window.addEventListener("open-cookie-settings", handleOpenSettings)
    return () => window.removeEventListener("open-cookie-settings", handleOpenSettings)
  }, [])

  const handleSaveConsent = (level: "necessary" | "all" | "custom") => {
    localStorage.setItem("opuslex_cookie_consent", level)
    setShowCookieBanner(false)
    setShowCookieModal(false)
  }

  return (
    <ErrorBoundary fallbackTitle="OpusLex Encountered an Application Error">
      <PreferencesProvider>
        {isLoggedIn ? (
          <Dashboard />
        ) : (
          <Auth onLoginSuccess={() => setIsLoggedIn(true)} />
        )}
      
      {showCookieBanner && !showCookieModal && (
        <div className="fixed bottom-6 right-6 z-[200] max-w-md rounded-xl border border-neutral-200 bg-white p-5 shadow-2xl flex flex-col gap-4">
          <p className="text-sm font-semibold text-neutral-900">Privacy & Preferences</p>
          <p className="text-xs text-neutral-600 leading-relaxed">
            OpusLex uses necessary browser storage to maintain core application functionality and your preferences. No optional analytics or marketing tracking technologies are currently configured.
          </p>
          <div className="flex justify-end gap-2 mt-1">
            <button
              onClick={() => setShowCookieModal(true)}
              className="rounded px-4 py-2 text-xs font-medium text-neutral-600 hover:bg-neutral-100 transition-colors"
            >
              Customize
            </button>
            <button
              onClick={() => handleSaveConsent("necessary")}
              className="rounded px-4 py-2 text-xs font-medium text-neutral-600 hover:bg-neutral-100 transition-colors"
            >
              Reject optional
            </button>
            <button
              onClick={() => handleSaveConsent("all")}
              className="rounded bg-neutral-900 px-4 py-2 text-xs font-medium text-white hover:bg-neutral-800 transition-colors"
            >
              Accept all
            </button>
          </div>
        </div>
      )}

      {showCookieModal && (
        <div className="fixed inset-0 z-[250] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg overflow-hidden flex flex-col max-h-[85vh]">
              <div className="flex items-center justify-between border-b border-neutral-100 p-4">
                  <h2 className="text-lg font-semibold text-neutral-900">Cookie preferences</h2>
                  <button
                      onClick={() => setShowCookieModal(false)}
                      className="rounded-full p-2 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 transition-colors"
                  >
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                  </button>
              </div>
              <div className="flex-1 overflow-y-auto p-5 space-y-6">
                  <div>
                      <div className="flex items-center justify-between mb-1">
                          <h3 className="text-sm font-semibold text-neutral-900">Necessary / Functional</h3>
                          <span className="text-xs font-medium text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full">Always active</span>
                      </div>
                      <p className="text-xs text-neutral-600">Required for core application functionality. Used to store your session and UI preferences.</p>
                  </div>
                  <div className="pt-4 border-t border-neutral-100 opacity-60">
                      <div className="flex items-center justify-between mb-1">
                          <h3 className="text-sm font-semibold text-neutral-900">Analytics</h3>
                          <span className="text-xs font-medium text-neutral-500 bg-neutral-100 px-2 py-0.5 rounded-full">Not configured</span>
                      </div>
                      <p className="text-xs text-neutral-600">No optional tracking technologies are currently configured.</p>
                  </div>
                  <div className="pt-4 border-t border-neutral-100 opacity-60">
                      <div className="flex items-center justify-between mb-1">
                          <h3 className="text-sm font-semibold text-neutral-900">Marketing</h3>
                          <span className="text-xs font-medium text-neutral-500 bg-neutral-100 px-2 py-0.5 rounded-full">Not configured</span>
                      </div>
                      <p className="text-xs text-neutral-600">No optional tracking technologies are currently configured.</p>
                  </div>
              </div>
              <div className="border-t border-neutral-100 p-4 flex justify-end">
                  <button
                      onClick={() => handleSaveConsent("custom")}
                      className="rounded bg-neutral-900 px-5 py-2 text-sm font-medium text-white hover:bg-neutral-800 transition-colors"
                  >
                      Save preferences
                  </button>
              </div>
          </div>
        </div>
      )}
      </PreferencesProvider>
    </ErrorBoundary>
  )
}

export default App