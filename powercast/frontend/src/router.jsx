import { useRoutes } from 'react-router-dom'
import Home from './pages/Home'
import NotFound from './pages/NotFound'
import DataImport from './pages/DataImport'
import DataCoverage from './pages/DataCoverage'
import Train from './pages/Train'
import Models from './pages/Models'
import Forecast from './pages/Forecast'
import ForecastsList from './pages/ForecastsList'
import Evaluate from './pages/Evaluate'



export default function Router(){
  return useRoutes([
    { path: '/', element: <Home /> },
    { path: '*', element: <NotFound /> },
    { path: '/import', element: <DataImport /> },
    { path: '/coverage', element: <DataCoverage /> },
    { path: '/train', element: <Train /> },
    { path: '/models', element: <Models /> },
    { path: '/forecast', element: <Forecast /> },
    { path: '/forecasts', element: <ForecastsList /> },
    { path: '/evaluate', element: <Evaluate /> },
  ])
}
