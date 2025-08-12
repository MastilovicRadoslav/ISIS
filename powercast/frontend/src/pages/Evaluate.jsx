import { useEffect, useState } from 'react'
import { Card, Typography, Select, Table, Button, Space, Alert } from 'antd'
import api from '../services/api'
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Legend } from 'recharts'

const { Title } = Typography
const REGIONS = ['N.Y.C.', 'LONGIL', 'CAPITL', 'CENTRL', 'DUNWOD', 'GENESE', 'HUD VL', 'MHK VL', 'MILLWD', 'NORTH', 'WEST']

export default function Evaluate(){
  const [region, setRegion] = useState('N.Y.C.')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(null)
  const [series, setSeries] = useState([])
  const [mapeMsg, setMapeMsg] = useState(null)

  const loadForecasts = async () => {
    setLoading(true)
    try{
      const res = await api.get('/api/forecast/search', { params: { region }})
      setRows((res.data.items || []).map((d,i)=>({ key:i, ...d })))
    }catch(e){/* noop */}
    finally{ setLoading(false) }
  }

  useEffect(()=>{ loadForecasts() }, [region])

  const columns = [
    { title: 'Start', dataIndex: 'start_date' },
    { title: 'Hours', dataIndex: 'horizon_h' },
    { title: 'Latest', dataIndex: 'is_latest', render: v => v ? 'Yes' : 'No' },
    { title: 'Action', render: (_,r) => <Button onClick={()=>selectForecast(r)}>Evaluate</Button> }
  ]

  const selectForecast = async (r) => {
    setSelected(r)
    setMapeMsg(null)
    // 1) Fetch forecast detail
    const f = await api.get(`/api/forecast/${r._id}`)
    const vals = f.data.forecast.values || []
    if (!vals.length){ return }
    const from = vals[0].ts, to = vals[vals.length-1].ts

    // 2) Fetch actual
    const fromISO = new Date(vals[0].ts).toISOString();
    const toISO = new Date(vals[vals.length - 1].ts).toISOString();
    const a = await api.get('/api/series/actual', { params: { region: r.region, from: fromISO, to: toISO }});

    // 3) Build merged series for chart (match by ts)
    const amap = new Map(a.data.items.map(it => [it.ts, it.load_mw]))
    const merged = vals.map(v => ({ ts: v.ts, forecast: v.yhat, actual: amap.get(v.ts) }))
    setSeries(merged)
    merged.sort((a,b) => new Date(a.ts) - new Date(b.ts));


    // 4) Ask backend for MAPE
    const m = await api.get('/api/metrics/mape/for-forecast', { params: { forecast_id: r._id }})
    setMapeMsg({ points: m.data.points, mape: m.data.mape, from: m.data.from, to: m.data.to })
  }

  return (
    <Card>
      <Title level={3}>Evaluate Forecasts</Title>
      <Space style={{ marginBottom: 12 }}>
        <Select value={region} onChange={setRegion} options={REGIONS.map(r=>({label:r,value:r}))} />
        <Button onClick={loadForecasts}>Refresh</Button>
      </Space>

      <Table loading={loading} columns={columns} dataSource={rows} size="small" pagination={{ pageSize: 8 }} />

      {mapeMsg && (
        <Alert type="info" style={{ marginTop: 12 }} message={`MAPE: ${mapeMsg.mape?.toFixed?.(2)}% (points=${mapeMsg.points})`} description={`${mapeMsg.from} → ${mapeMsg.to}`} />
      )}

      <div style={{ width:'100%', height:360, marginTop: 12 }}>
        <ResponsiveContainer>
          <LineChart data={series}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="ts" minTickGap={24} />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="actual" dot={false} />
            <Line type="monotone" dataKey="forecast" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}