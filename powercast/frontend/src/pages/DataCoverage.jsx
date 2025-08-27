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
  const columnsHolidays = [
    { title: 'Region', dataIndex: 'region', key: 'region' },
    { title: 'From', dataIndex: 'from', key: 'from' },
    { title: 'To', dataIndex: 'to', key: 'to' },
    { title: 'Days', dataIndex: 'days', key: 'days' }
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

  const columns =
    type === 'load' ? columnsLoad :
    type === 'weather' ? columnsWeather :
    columnsHolidays

  return (
    <Card>
      <Space direction="vertical" style={{ width: '100%' }}>
        <Title level={3}>Data Coverage</Title>
        <Segmented
          value={type}
          onChange={setType}
          options={[
            {label:'Load', value:'load'},
            {label:'Weather', value:'weather'},
            {label:'Holidays', value:'holidays'},
          ]}
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
                <div><b>Holidays</b>: {summary.holidays.exists ? `${summary.holidays.from} → ${summary.holidays.to} (${summary.holidays.days} days, ${summary.holidays.keys} region)` : 'no data'}</div>
              </div>
            }
          />
        )}
        <Table
          size="small"
          loading={loading}
          columns={columns}
          dataSource={rows.map((r,i)=>({key:i,...r}))}
          pagination={{ pageSize: 10 }}
        />
      </Space>
    </Card>
  )
}
