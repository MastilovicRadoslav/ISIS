import { Card, Typography, Alert } from 'antd'
import api from '../services/api'
import { useEffect, useState } from 'react'

const { Title, Paragraph } = Typography

export default function Home(){
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/api/health')
      .then(res => setHealth(res.data))
      .catch(err => setError(err.message))
  }, [])

  return (
    <Card>
      <Title level={3}>Welcome to PowerCast</Title>
      <Paragraph>Sprint 0: test konekcije frontend ↔ backend ↔ Mongo.</Paragraph>
      {health && <Alert type="success" message={`Backend OK: ${JSON.stringify(health)}`} />}
      {error && <Alert type="error" message={error} />}
    </Card>
  )
}
