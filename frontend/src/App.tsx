import {BrowserRouter as Router, Link, Route, Routes} from "react-router-dom";
import ClosePulseAI from "./compontens/VoiceAssistant.tsx";
import AdminPage from "./screen/AdminPage.tsx";

function App() {
    return (
        <Router>
            <nav>
                <Link to="/">Voice Assistant</Link> | <Link to="/admin">Admin</Link>
            </nav>
            <Routes>
                <Route path="/" element={<ClosePulseAI/>}/>
                <Route path="/admin" element={<AdminPage/>}/>
            </Routes>
        </Router>
    );
}

export default App;
