import { useEffect, useState } from 'react'
import { Card, Typography, Table, Select, Space, Button, message } from 'antd'
import api from '../services/api'

const { Title } = Typography
const REGIONS = ['N.Y.C.', 'LONGIL', 'CAPITL', 'CENTRL', 'DUNWOD', 'GENESE', 'HUD VL', 'MHK VL', 'MILLWD', 'NORTH', 'WEST']

export default function Models(){
  const [region, setRegion] = useState('N.Y.C.')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try{
      const res = await api.get('/api/model/list', { params: { region }})
      setRows((res.data.models || []).map((m,i)=>({ key:i, ...m })))
    }catch(e){
      message.error(e.response?.data?.error || e.message)
    }finally{ setLoading(false) }
  }

  useEffect(()=>{ load() }, [region])

  const columns = [
    { title: 'Region', dataIndex: 'region' },
    { title: 'Algo', dataIndex: 'algo' },
    { title: 'Train From', dataIndex: ['train_range','from'] },
    { title: 'Train To', dataIndex: ['train_range','to'] },
    { title: 'Val Loss', dataIndex: ['metrics','val_loss'] },
    { title: 'Test MAPE', dataIndex: ['metrics','test_mape'] },
    { title: 'Created', dataIndex: 'created_at' }
  ]

  return (
    <Card>
      <Title level={3}>Models</Title>
      <Space style={{ marginBottom: 12 }}>
        <Select value={region} onChange={setRegion} options={REGIONS.map(r=>({label:r,value:r}))} />
        <Button onClick={load}>Refresh</Button>
      </Space>
      <Table loading={loading} columns={columns} dataSource={rows} size="small" />
    </Card>
  )
}