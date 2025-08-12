import { useState } from 'react'
import { Card, Typography, Radio, Upload, Button, List, Alert, Tag } from 'antd'
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
    beforeUpload: () => false, // ne uploaduj automatski
    fileList,
    onChange: ({ fileList }) => setFileList(fileList),
    accept: '.csv,.xlsx,.xls',
  }

  const getEndpoint = (t) => {
    if (t === 'load') return '/api/import/load'
    if (t === 'weather') return '/api/import/weather'
    if (t === 'holidays') return '/api/import/holidays'
    return ''
  }

  const onUpload = async ({ fileList }) => {
    if (!fileList || fileList.length === 0) return

    setError(null)
    setUploading(true)

    const endpoint = getEndpoint(type)
    const files = fileList.map(f => f.originFileObj)

    const newResults = []

    for (const file of files) {
      const form = new FormData()
      form.append('file', file, file.name)
      try {
        const res = await api.post(endpoint, form, {
          headers: { 'Content-Type': 'multipart/form-data' }
        })
        newResults.push({ ok: true, file: file.name, data: res.data, t: type })
      } catch (e) {
        newResults.push({
          ok: false,
          file: file.name,
          error: e.response?.data?.error || e.message,
          t: type
        })
      }
    }

    // deduplikuj po (file, range, ok, type)
    setResults(prev => {
      const merged = [...newResults, ...prev] // noviji gore
      const seen = new Set()
      return merged.filter(r => {
        const from = r.data?.ts_range?.from || r.data?.range?.from || ''
        const to = r.data?.ts_range?.to || r.data?.range?.to || ''
        const key = `${r.t}|${r.file}|${from}|${to}|${r.ok ? '1' : '0'}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
    })

    setUploading(false)
    setFileList([]) // reset liste nakon uspješnog uploada
  }

  const renderLine = (item) => {
    if (!item.ok) {
      return (
        <div>
          <b>{item.file}</b> → <Tag color="error">ERROR</Tag> {item.error}
        </div>
      )
    }

    const isHolidays = item.t === 'holidays'
    if (isHolidays) {
      const regions = item.data.regions || []
      return (
        <div>
          <b>{item.file}</b> → <Tag color="success">OK</Tag> • rows: {item.data.rows} • regions: {regions.length ? regions.join(', ') : '—'}
        </div>
      )
    }

    // load/weather
    const rangeFrom = item.data.ts_range?.from
    const rangeTo = item.data.ts_range?.to
    const rows = item.data.rows_hourly
    const upserts = item.data.upserts
    const modified = item.data.modified
    const regions = item.data.regions || item.data.locations || []

    return (
      <div>
        <b>{item.file}</b> → <Tag color="success">OK</Tag> • rows_hourly: {rows} • upserts: {upserts} • modified: {modified} • range: {rangeFrom} → {rangeTo}
        {regions.length > 0 && (
          <div style={{ marginTop: 4 }}>
            regions ({regions.length}): {regions.join(', ')}
          </div>
        )}
        {(upserts === 0 && modified === 0) && (
          <div style={{ marginTop: 4 }}>
            <Tag>no changes</Tag>
          </div>
        )}
      </div>
    )
  }

  return (
    <Card>
      <Title level={3}>Data Import</Title>
      <Paragraph>
        Odaberi tip CSV/Excel fajla i pošalji jedan ili više fajlova. Backend će upisati
        <b> satne </b> ili <b> dnevne </b> vrijednosti u Mongo.
      </Paragraph>

      <Radio.Group
        value={type}
        onChange={e => {
          setType(e.target.value)
          setResults([])
          setFileList([])
          setError(null)
        }}
        style={{ marginBottom: 16 }}
      >
        <Radio.Button value="load">Load (NYISO 5-min → 1h mean)</Radio.Button>
        <Radio.Button value="weather">Weather (1h)</Radio.Button>
        <Radio.Button value="holidays">Holidays (daily)</Radio.Button>
      </Radio.Group>

      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <Upload {...uploadProps} disabled={uploading}>
          <Button icon={<UploadOutlined />} disabled={uploading}>
            {uploading ? 'Uploading...' : 'Select CSV/Excel files'}
          </Button>
        </Upload>

        <Button
          type="primary"
          loading={uploading}
          disabled={uploading || fileList.length === 0}
          onClick={() => onUpload({ fileList })}
        >
          {uploading ? 'Uploading...' : 'Start upload'}
        </Button>

        <Button
          disabled={uploading && fileList.length === 0}
          onClick={() => setFileList([])}
        >
          Clear selection
        </Button>
      </div>

      {error && <Alert type="error" message={error} style={{ marginTop: 8 }} />}

      <List
        style={{ marginTop: 16 }}
        header={<div>Rezultati uvoza (noviji gore)</div>}
        bordered
        dataSource={results}
        renderItem={(item, idx) => (
          <List.Item key={`${item.t}-${item.file}-${item.data?.ts_range?.from || ''}-${item.data?.ts_range?.to || ''}-${item.ok}-${idx}`}>
            {renderLine(item)}
          </List.Item>
        )}
      />
    </Card>
  )
}
