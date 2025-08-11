import { useState } from 'react'
import { Card, Typography, Radio, Upload, Button, List, Alert } from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import api from '../services/api'

const { Title, Paragraph } = Typography

export default function DataImport() {
  const [type, setType] = useState('load')
  const [results, setResults] = useState([])
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [fileList, setFileList] = useState([])

  const uploadProps = {
    multiple: true,
    beforeUpload: () => false,
    fileList,
    onChange: ({ fileList }) => setFileList(fileList)
  }

  const onUpload = async ({ fileList }) => {
    if (fileList.length === 0) return

    setError(null)
    setUploading(true)

    const files = fileList.map(f => f.originFileObj)
    const endpoint = type === 'load' ? '/api/import/load' : '/api/import/weather'
    const newResults = []

    for (const file of files) {
      const form = new FormData()
      form.append('file', file, file.name)
      try {
        const res = await api.post(endpoint, form, {
          headers: { 'Content-Type': 'multipart/form-data' }
        })
        newResults.push({ ok: true, file: file.name, data: res.data })
      } catch (e) {
        newResults.push({
          ok: false,
          file: file.name,
          error: e.response?.data?.error || e.message
        })
      }
    }

    setResults(prev => [...newResults, ...prev])
    setUploading(false)
    setFileList([]) // resetuje fajlove nakon uploada
  }

  return (
    <Card>
      <Title level={3}>Data Import</Title>
      <Paragraph>
        Odaberi tip CSV fajla i pošalji jedan ili više fajlova. Backend će upisati
        <b> satne </b> vrijednosti u Mongo.
      </Paragraph>

      <Radio.Group
        value={type}
        onChange={e => {
          setType(e.target.value)
          setResults([])
          setFileList([])
        }}
        style={{ marginBottom: 16 }}
      >
        <Radio.Button value="load">Load (NYISO 5-min → 1h mean)</Radio.Button>
        <Radio.Button value="weather">Weather (1h)</Radio.Button>
      </Radio.Group>

      <Upload {...uploadProps} onChange={onUpload} disabled={uploading}>
        <Button icon={<UploadOutlined />} loading={uploading}>
          {uploading ? 'Uploading...' : 'Select CSV files'}
        </Button>
      </Upload>

      {error && <Alert type="error" message={error} style={{ marginTop: 16 }} />}

      <List
        style={{ marginTop: 16 }}
        header={<div>Rezultati uvoza (noviji gore)</div>}
        bordered
        dataSource={results}
        renderItem={(item) => (
          <List.Item>
            {item.ok ? (
              <div>
                <b>{item.file}</b> → OK • rows_hourly: {item.data.rows_hourly} • range:{' '}
                {item.data.ts_range.from} → {item.data.ts_range.to}
              </div>
            ) : (
              <div>
                <b>{item.file}</b> → ERROR: {item.error}
              </div>
            )}
          </List.Item>
        )}
      />
    </Card>
  )
}
