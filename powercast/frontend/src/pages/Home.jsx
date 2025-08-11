import { useEffect, useMemo, useState } from "react";
import { Card, Typography, Alert, Spin, Tag, Space, Divider } from "antd";
import { CheckCircleTwoTone, ExclamationCircleTwoTone, CloudServerOutlined } from "@ant-design/icons";
import api from "../services/api";
import "../styles/home.css";

const { Title, Paragraph, Text } = Typography;

export default function Home() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const prettyHealth = useMemo(() => (health ? JSON.stringify(health, null, 2) : ""), [health]);

  useEffect(() => {
    let mounted = true;

    const fetchHealth = async () => {
      try {
        setLoading(true);
        const res = await api.get("/api/health", { timeout: 6000 });
        if (!mounted) return;
        setHealth(res.data);
        setError(null);
      } catch (err) {
        if (!mounted) return;
        const msg =
          err?.response?.data?.message ||
          err?.message ||
          "Unable to reach backend.";
        setError(msg);
        setHealth(null);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    fetchHealth();
    return () => { mounted = false; };
  }, []);

  return (
    <div className="home-page">
      <div className="hero-layer" />

      <Card className="home-card">
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          <Space align="center">
            <CloudServerOutlined className="home-icon" />
            <Title level={3} style={{ margin: 0 }}>PowerCast - short-term forecast of electricity consumption</Title>
          </Space>

          <Paragraph className="home-subtitle">
            <Text type="secondary">Frontend ↔ Backend ↔ MongoDB</Text>
          </Paragraph>

          <Divider className="home-divider" />

          {loading && <Spin tip="Checking backend health..." />}

          {!loading && health && (
            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
              <Alert
                type="success"
                showIcon
                message={
                  <Space>
                    <CheckCircleTwoTone twoToneColor="#52c41a" />
                    <span>Backend is reachable</span>
                  </Space>
                }
                description={
                  <Space size={[8, 8]} wrap>
                    <Tag color="success">status: OK</Tag>
                    {health?.db && <Tag>db: {String(health.db)}</Tag>}
                    {health?.service && <Tag>{health.service}</Tag>}
                    {health?.version && <Tag color="blue">v{health.version}</Tag>}
                  </Space>
                }
              />

              <Card size="small" bordered>
                <Paragraph style={{ marginBottom: 0 }}>
                  <Text type="secondary">Raw response</Text>
                </Paragraph>
                <pre className="home-pre">{prettyHealth}</pre>
              </Card>
            </Space>
          )}

          {!loading && error && (
            <Alert
              type="error"
              showIcon
              message={
                <Space>
                  <ExclamationCircleTwoTone twoToneColor="#ff4d4f" />
                  <span>Backend is not reachable</span>
                </Space>
              }
              description={
                <Space direction="vertical" size={4}>
                  <Text>{error}</Text>
                  <Text type="secondary">
                    Ensure API base URL and CORS are configured. Try running the backend and MongoDB.
                  </Text>
                </Space>
              }
            />
          )}

          <Divider className="home-divider" />

          <Paragraph className="home-footer">
            <Text type="secondary">This is the entry point. Use the top navigation to continue.</Text>
          </Paragraph>
        </Space>
      </Card>
    </div>
  );
}
