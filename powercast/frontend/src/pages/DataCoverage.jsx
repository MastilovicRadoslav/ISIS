import { useEffect, useState } from 'react'
import { Card, Typography, Segmented, Table, Space, Alert } from 'antd'
import api from '../services/api'

const { Title } = Typography

export default function DataCoverage(){
  const [type, setType] = useState('load')
  const [rows, setRows] = useState([])
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const columnsLoad = [
    { title: 'Region', dataIndex: 'region', key: 'region' },
    { title: 'From', dataIndex: 'from', key: 'from' },
    { title: 'To', dataIndex: 'to', key: 'to' },
    { title: 'Hours', dataIndex: 'hours', key: 'hours' }
  ]
  const columnsWeather = [
    { title: 'Location', dataIndex: 'location', key: 'location' },
    { title: 'From', dataIndex: 'from', key: 'from' },
    { title: 'To', dataIndex: 'to', key: 'to' },
    { title: 'Hours', dataIndex: 'hours', key: 'hours' }
  ]

  const loadData = async (t) => {
    setLoading(true); setError(null)
    try {
      const [cov, sum] = await Promise.all([
        api.get('/api/series/coverage', { params: { type: t }}),
        api.get('/api/series/coverage/summary')
      ])
      setRows(cov.data.coverage || [])
      setSummary(sum.data || null)
    } catch (e) {
      setError(e.response?.data?.error || e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData(type) }, [type])

  return (
    <Card>
      <Space direction="vertical" style={{ width: '100%' }}>
        <Title level={3}>Data Coverage</Title>
        <Segmented
          value={type}
          onChange={setType}
          options={[{label:'Load', value:'load'},{label:'Weather', value:'weather'}]}
        />
        {error && <Alert type="error" message={error} />}
        {summary && (
          <Alert
            type="info"
            showIcon
            message="Summary"
            description={
              <div>
                <div><b>Load</b>: {summary.load.exists ? `${summary.load.from} → ${summary.load.to} (${summary.load.hours}h, ${summary.load.keys} regiona)` : 'no data'}</div>
                <div><b>Weather</b>: {summary.weather.exists ? `${summary.weather.from} → ${summary.weather.to} (${summary.weather.hours}h, ${summary.weather.keys} lokacija)` : 'no data'}</div>
              </div>
            }
          />
        )}
        <Table
          size="small"
          loading={loading}
          columns={type === 'load' ? columnsLoad : columnsWeather}
          dataSource={rows.map((r,i)=>({key:i,...r}))}
          pagination={{ pageSize: 10 }}
        />
      </Space>
    </Card>
  )
}
