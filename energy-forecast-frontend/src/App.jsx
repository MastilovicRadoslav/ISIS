import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import UploadPage from "./pages/UploadPage";

const App = () => {
  return (
    <Router>
      <Navbar />
      <Routes>
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/" element={<UploadPage />} /> {/* privremeno */}
      </Routes>
    </Router>
  );
};

export default App;
