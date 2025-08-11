import { useEffect, useState } from 'react'
import { Card, Typography, Table, Select, DatePicker, Button, Space, message } from 'antd'
import api from '../services/api'

const { Title } = Typography
const { RangePicker } = DatePicker
const REGIONS = ['N.Y.C.', 'LONGIL', 'CAPITL', 'CENTRL', 'DUNWOD', 'GENESE', 'HUD VL', 'MHK VL', 'MILLWD', 'NORTH', 'WEST']

export default function ForecastsList(){
  const [region, setRegion] = useState()
  const [range, setRange] = useState()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try{
      const params = {}
      if (region) params.region = region
      if (range) { params.date_from = range[0].startOf('day').toISOString(); params.date_to = range[1].endOf('day').toISOString() }
      const res = await api.get('/api/forecast/search', { params })
      setRows((res.data.items || []).map((d,i)=>({ key:i, ...d })))
    }catch(e){
      message.error(e.response?.data?.error || e.message)
    }finally{ setLoading(false) }
  }

  useEffect(()=>{ load() }, [])

  const columns = [
    { title: 'Region', dataIndex: 'region' },
    { title: 'Start', dataIndex: 'start_date' },
    { title: 'Hours', dataIndex: 'horizon_h' },
    { title: 'Latest', dataIndex: 'is_latest', render: v => v ? 'Yes' : 'No' },
    { title: 'Export', dataIndex: 'export_id', render: (v)=> v ? <a href={`${import.meta.env.VITE_API_URL}/api/forecast/export/${v}`}>CSV</a> : '-' }
  ]

  return (
    <Card>
      <Title level={3}>Forecasts</Title>
      <Space style={{ marginBottom: 12 }}>
        <Select allowClear placeholder="Region" value={region} onChange={setRegion} options={REGIONS.map(r=>({label:r,value:r}))} />
        <RangePicker value={range} onChange={setRange} />
        <Button onClick={load}>Search</Button>
      </Space>
      <Table loading={loading} columns={columns} dataSource={rows} size="small" />
    </Card>
  )
}