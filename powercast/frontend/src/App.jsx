import { Layout, Menu, theme } from 'antd'
import { Link } from 'react-router-dom'
import Router from './router'

const { Header, Content, Footer } = Layout

export default function App(){
  const { token: { colorBgContainer, borderRadiusLG } } = theme.useToken()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center' }}>
        <div style={{ color: '#fff', fontWeight: 700, marginRight: 24 }}>PowerCast</div>
        <Menu
          theme="dark"
          mode="horizontal"
          defaultSelectedKeys={['home']}
          items={[ { key: 'home', label: <Link to="/">Home</Link> }, 
                   { key: 'import', label: <Link to="/import">Data Import</Link> },
                   { key: 'coverage', label: <Link to="/coverage">Coverage</Link> },  
                   { key: 'train', label: <Link to="/train">Train</Link> },
                   { key: 'models', label: <Link to="/models">Models</Link> },
                   { key: 'forecast', label: <Link to="/forecast">Forecast</Link> },
                   { key: 'forecasts', label: <Link to="/forecasts">Forecasts</Link> },
                ]}
        />
      </Header>
      <Content style={{ padding: '24px' }}>
        <div style={{ background: colorBgContainer, minHeight: 380, padding: 24, borderRadius: borderRadiusLG }}>
          <Router />
        </div>
      </Content>
      <Footer style={{ textAlign: 'center' }}>© {new Date().getFullYear()} PowerCast</Footer>
    </Layout>
  )
}
