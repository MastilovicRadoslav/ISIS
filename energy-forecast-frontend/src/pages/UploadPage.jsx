import React, { useState, useEffect } from "react";
import { Upload, Button, message, Typography } from "antd";
import { UploadOutlined } from "@ant-design/icons";
import api from "../services/api";
import "../styles/uploadPage.css";


const { Title } = Typography;

const UploadPage = () => {
    const [fileList, setFileList] = useState([]);
    const [uploading, setUploading] = useState(false);

    const props = {
        multiple: true,
        accept: ".csv",
        onRemove: (file) => {
            setFileList((prevList) => prevList.filter((f) => f.uid !== file.uid));
        },
        beforeUpload: (file) => {
            setFileList((prevList) => [...prevList, file]);
            return false;
        },
    };


    const handleUpload = async () => {
        const formData = new FormData();
        fileList.forEach((file) => {
            formData.append("files", file);
        });

        setUploading(true);

        try {
            const response = await api.post("/upload", formData);
            const inserted = response?.data?.inserted ?? 0;

            if (inserted > 0) {
                alert("✅ Uspješno uploadovano!");

                setFileList([]);
            }


        } catch (error) {
            console.error(error);
            message.error("❌ Upload failed.");
        } finally {
            setUploading(false);
        }
    };
    return (
        <div className="upload-page-container">
            <div className="upload-card">
                <Title level={3} className="upload-title">Upload CSV Files</Title>
                <Upload {...props} fileList={fileList} key={fileList.length}>
                    <Button icon={<UploadOutlined />}>Select CSV Files</Button>
                </Upload>

                <Button
                    type="primary"
                    onClick={handleUpload}
                    disabled={fileList.length === 0}
                    loading={uploading}
                    className="upload-button"
                >
                    Upload
                </Button>
            </div>
        </div>
    );
};

export default UploadPage;
