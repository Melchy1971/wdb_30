import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import ImportPage from './pages/ImportPage'
import AnalysisPage from './pages/AnalysisPage'

export default function App() {
  return (
    <BrowserRouter>
      <nav style={{ padding: '1rem', borderBottom: '1px solid #ccc', display: 'flex', gap: '1rem' }}>
        <NavLink to="/">Dashboard</NavLink>
        <NavLink to="/imports">Importe</NavLink>
        <NavLink to="/analysis">Analyse</NavLink>
      </nav>
      <main style={{ padding: '1rem' }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/imports" element={<ImportPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
