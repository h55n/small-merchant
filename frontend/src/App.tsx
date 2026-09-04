import { Routes, Route, Outlet } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import Nav from './components/Nav'
import { ErrorBoundary } from './components/ErrorBoundary'

const Landing = lazy(() => import('./pages/Landing'))
const MerchantPage = lazy(() => import('./pages/MerchantPage'))
const BuyerPage = lazy(() => import('./pages/BuyerPage'))
const EvalPage = lazy(() => import('./pages/EvalPage'))
const AuditPage = lazy(() => import('./pages/AuditPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))

function LoadingFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="flex gap-1">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
    </div>
  )
}

function AppLayout() {
  return (
    <>
      <Nav />
      <main className="max-w-[1200px] mx-auto px-6 py-8">
        <ErrorBoundary fallbackTitle="Could not render page">
          <Suspense fallback={<LoadingFallback />}>
            <Outlet />
          </Suspense>
        </ErrorBoundary>
      </main>
    </>
  )
}

export default function App() {
  return (
    <ErrorBoundary fallbackTitle="Application Error">
      <div className="min-h-screen bg-white font-sans text-neutral-900">
        <Routes>
          <Route
            path="/"
            element={
              <Suspense fallback={<LoadingFallback />}>
                <Landing />
              </Suspense>
            }
          />
          <Route element={<AppLayout />}>
            <Route path="/merchant" element={<MerchantPage />} />
            <Route path="/buyer" element={<BuyerPage />} />
            <Route path="/evaluate" element={<EvalPage />} />
            <Route path="/audit/:sessionId" element={<AuditPage />} />
            <Route path="/audit" element={<AuditPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
          </Route>
        </Routes>
      </div>
    </ErrorBoundary>
  )
}

