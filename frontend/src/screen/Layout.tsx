import {BrowserRouter as Router, Route, Routes} from "react-router-dom";
import React from "react";
import ClosePulseAI from "../compontens/VoiceAssistant.tsx";
import AdminPage from "./AdminPage.tsx";
import Header from "../compontens/header/Header.tsx";

const Layout: React.FC = () => {
    return (
        <Router>
            <Header/>
            <Routes>
                <Route path="/" element={<ClosePulseAI/>}/>
                <Route path="/admin" element={<AdminPage/>}/>
            </Routes>
        </Router>
    );
}

export default Layout;
