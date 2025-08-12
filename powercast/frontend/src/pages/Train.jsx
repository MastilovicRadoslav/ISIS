import { useState } from 'react'
import { Card, Typography, Form, InputNumber, Select, DatePicker, Button, message } from 'antd'
import api from '../services/api'

const { Title } = Typography
const { RangePicker } = DatePicker

const REGIONS = [
  'N.Y.C.', 'LONGIL', 'CAPITL', 'CENTRL', 'DUNWOD',
  'GENESE', 'HUD VL', 'MHK VL', 'MILLWD', 'NORTH', 'WEST'
]

export default function Train() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)

  const onFinish = async (values) => {
    if (!values.range || values.range.length !== 2) {
      message.error('Please select a date range.')
      return
    }
    setLoading(true)
    const hide = message.loading('Training model... please wait', 0)
    try {
      const [from, to] = values.range
      const body = {
        regions: values.regions,
        date_from: from.toDate().toISOString(),
        date_to: to.toDate().toISOString(),
        hyper: {
          model: 'LSTM',
          layers: values.layers,
          hidden_size: values.hidden_size,
          dropout: values.dropout,
          epochs: values.epochs,
          batch_size: values.batch_size,
          learning_rate: values.learning_rate,
          input_window: values.input_window,
          forecast_horizon: values.forecast_horizon,
          teacher_forcing: values.teacher_forcing
        }
      }
      const res = await api.post('/api/train/start', body)
      hide()
      message.success('Training finished and model saved!')
      console.log(res.data)
    } catch (e) {
      hide()
      message.error(e.response?.data?.error || e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <Title level={3}>Train Model</Title>
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        initialValues={{
          regions: ['N.Y.C.', 'LONGIL'],
          layers: 2,
          hidden_size: 128,
          dropout: 0.2,
          epochs: 10,
          batch_size: 64,
          learning_rate: 0.001,
          input_window: 168,
          forecast_horizon: 168,
          teacher_forcing: 0.2
        }}
      >
        <Form.Item name="regions" label="Regions" rules={[{ required: true }]}>
          <Select
            mode="multiple"
            options={REGIONS.map(r => ({ label: r, value: r }))}
            placeholder="Select one or more regions"
          />
        </Form.Item>

        <Form.Item name="range" label="Date range" rules={[{ required: true }]}>
          <RangePicker showTime />
        </Form.Item>

        <Form.Item name="layers" label="Layers">
          <InputNumber min={1} max={4} />
        </Form.Item>

        <Form.Item name="hidden_size" label="Hidden size">
          <InputNumber min={16} max={512} />
        </Form.Item>

        <Form.Item name="dropout" label="Dropout">
          <InputNumber min={0} max={0.9} step={0.1} />
        </Form.Item>

        <Form.Item name="epochs" label="Epochs">
          <InputNumber min={1} max={200} />
        </Form.Item>

        <Form.Item name="batch_size" label="Batch size">
          <InputNumber min={8} max={512} />
        </Form.Item>

        <Form.Item name="learning_rate" label="Learning rate">
          <InputNumber min={0.00001} max={0.1} step={0.0005} />
        </Form.Item>

        <Form.Item name="input_window" label="Input window (h)">
          <InputNumber min={24} max={336} />
        </Form.Item>

        <Form.Item name="forecast_horizon" label="Horizon (h)">
          <InputNumber min={24} max={168} />
        </Form.Item>

        <Form.Item name="teacher_forcing" label="Teacher forcing (0-1)">
          <InputNumber min={0} max={1} step={0.1} />
        </Form.Item>

        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>
            Train
          </Button>
        </Form.Item>
      </Form>
    </Card>
  )
}
