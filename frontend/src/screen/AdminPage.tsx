import React, {useEffect, useState} from "react";
import {Box, Button, ToggleButton, ToggleButtonGroup, Typography} from "@mui/material";
import {makeStyles} from "tss-react/mui";

const useStyles = makeStyles()(() => ({
    root: {
        height: "100vh",
        width: "100vw",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#fafafa",
        padding: "2rem",
        fontFamily: "'Helvetica Neue', Helvetica, Arial, sans-serif",
    },
    container: {
        background: "#fff",
        borderRadius: 12,
        padding: "2rem",
        boxShadow: "0 8px 24px rgba(0,0,0,0.1)",
        maxWidth: 600,
        width: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "1.5rem",
        textAlign: "center",
    },
    button: {
        padding: "1rem 2rem",
        fontSize: "1rem",
        borderRadius: 50,
        backgroundColor: "#FF6F61",
        color: "#fff",
        "&:hover": {
            backgroundColor: "#e05a4f",
        },
    },
    toggleGroup: {
        backgroundColor: "#f0f0f0",
        borderRadius: 8,
        padding: "0.2rem",
    },
}));

const AdminPage: React.FC = () => {
    const {classes} = useStyles();
    const [mode, setMode] = useState<"localMic" | "webRTC">("localMic");
    const [savedMessage, setSavedMessage] = useState<string | null>(null);

    useEffect(() => {
        const configRaw = localStorage.getItem("voiceAssistantConfig");
        if (configRaw) {
            try {
                const config = JSON.parse(configRaw);
                if (config.mode === "webrtc") setMode("webRTC");
                else setMode("localMic");
            } catch {
                setMode("localMic");
            }
        }
    }, []);

    const handleModeChange = (
        event: React.MouseEvent<HTMLElement>,
        newMode: "localMic" | "webRTC" | null
    ) => {
        if (newMode !== null) setMode(newMode);
    };

    const handleSave = () => {
        const config = {
            mode: mode === "webRTC" ? "webrtc" : "local",
        };
        localStorage.setItem("voiceAssistantConfig", JSON.stringify(config));
        setSavedMessage("Einstellungen gespeichert!");
        setTimeout(() => setSavedMessage(null), 3000);
    };

    return (
        <Box className={classes.root}>
            <Box className={classes.container}>
                <Typography variant="h4" gutterBottom>
                    Admin Einstellungen
                </Typography>

                <Typography variant="subtitle1" gutterBottom>
                    Wähle den Eingabemodus für ClosePulseAI:
                </Typography>

                <ToggleButtonGroup
                    value={mode}
                    exclusive
                    onChange={handleModeChange}
                    className={classes.toggleGroup}
                    aria-label="Eingabemodus auswählen"
                >
                    <ToggleButton value="localMic" aria-label="Lokales Mikrofon">
                        Lokales Mikrofon
                    </ToggleButton>
                    <ToggleButton value="webRTC" aria-label="WebRTC">
                        WebRTC
                    </ToggleButton>
                </ToggleButtonGroup>

                <Button onClick={handleSave} className={classes.button}>
                    Speichern
                </Button>

                {savedMessage && (
                    <Typography variant="body2" color="success.main" sx={{mt: 1}}>
                        {savedMessage}
                    </Typography>
                )}
            </Box>
        </Box>
    );
};

export default AdminPage;
