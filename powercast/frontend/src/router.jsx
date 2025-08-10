import { useRoutes } from 'react-router-dom'
import Home from './pages/Home'
import NotFound from './pages/NotFound'
import DataImport from './pages/DataImport'
import DataCoverage from './pages/DataCoverage'


export default function Router(){
  return useRoutes([
    { path: '/', element: <Home /> },
    { path: '*', element: <NotFound /> },
    { path: '/import', element: <DataImport /> },
    { path: '/coverage', element: <DataCoverage /> },
  ])
}
