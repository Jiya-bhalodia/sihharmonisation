import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'

import DashboardPage from './pages/DashboardPage'
import DataSourcesPage from './pages/DataSourcesPage'
import HarmonizationPage from './pages/HarmonizationPage'
import SpatialMatchingPage from './pages/SpatialMatchingPage'
import ConflictsPage from './pages/ConflictsPage'
import TopologyPage from './pages/TopologyPage'
import ChangesPage from './pages/ChangesPage'
import RecordsPage from './pages/RecordsPage'
import ReportsPage from './pages/ReportsPage'
import SystemStatusPage from './pages/SystemStatusPage'
import SettingsPage from './pages/SettingsPage'
import PilotReadinessPage from './pages/PilotReadinessPage'

export default function App() {
  return (
    <div className="min-h-screen bg-ink-50">
      <Sidebar />
      <main className="ml-64 min-h-screen">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/data-sources" element={<DataSourcesPage />} />
          <Route path="/harmonization" element={<HarmonizationPage />} />
          <Route path="/spatial-matching" element={<SpatialMatchingPage />} />
          <Route path="/conflicts" element={<ConflictsPage />} />
          <Route path="/topology" element={<TopologyPage />} />
          <Route path="/changes" element={<ChangesPage />} />
          <Route path="/records" element={<RecordsPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/system" element={<SystemStatusPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/pilot-readiness" element={<PilotReadinessPage />} />
        </Routes>
      </main>
    </div>
  )
}
