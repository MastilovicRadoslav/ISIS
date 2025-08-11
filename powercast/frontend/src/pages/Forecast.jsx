import { useState } from 'react'
import { Card, Typography, DatePicker, Select, InputNumber, Button, Alert } from 'antd'
import api from '../services/api'
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts'

const { Title } = Typography
const REGIONS = ['N.Y.C.', 'LONGIL', 'CAPITL', 'CENTRL', 'DUNWOD', 'GENESE', 'HUD VL', 'MHK VL', 'MILLWD', 'NORTH', 'WEST']

export default function Forecast(){
  const [region, setRegion] = useState('N.Y.C.')
  const [date, setDate] = useState(null)
  const [days, setDays] = useState(7)
  const [data, setData] = useState([])
  const [msg, setMsg] = useState(null)
  const [loading, setLoading] = useState(false)

  const run = async () => {
    setLoading(true); setMsg(null)
    try{
      const body = { region, start_date: date.startOf('hour').toISOString(), days }
      const res = await api.post('/api/forecast/run', body)
      const fid = res.data.forecast_id
      const f = await api.get(`/api/forecast/${fid}`)
      const series = (f.data.forecast.values || []).map(v => ({ ts: v.ts, yhat: v.yhat }))
      setData(series)
      setMsg({ type:'success', text: `Forecast OK (${series.length} points).` })
    }catch(e){
      setMsg({ type:'error', text: e.response?.data?.error || e.message })
    }finally{ setLoading(false) }
  }

  return (
    <Card>
      <Title level={3}>Forecast</Title>
      <div style={{ display:'flex', gap:12, flexWrap:'wrap', marginBottom:12 }}>
        <Select style={{ width:220 }} value={region} onChange={setRegion} options={REGIONS.map(r=>({label:r,value:r}))} />
        <DatePicker showTime value={date} onChange={setDate} />
        <InputNumber min={1} max={7} value={days} onChange={setDays} />
        <Button type="primary" onClick={run} disabled={!date} loading={loading}>Run forecast</Button>
      </div>
      {msg && <Alert type={msg.type} message={msg.text} style={{ marginBottom:12 }} />}
      <div style={{ width:'100%', height:360 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="ts" minTickGap={24} />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="yhat" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}