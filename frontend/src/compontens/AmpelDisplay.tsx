import React from "react";
import {Box, Typography} from "@mui/material";
import {makeStyles} from "tss-react/mui";

const useAmpelStyles = makeStyles()(() => ({
    root: {
        width: 80,
        height: 220,
        backgroundColor: "#222",
        borderRadius: 20,
        padding: 16,
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-around",
        alignItems: "center",
        boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
        marginTop: 16,
    },
    light: {
        width: 50,
        height: 50,
        borderRadius: "50%",
        transition: "all 0.3s ease",
        boxShadow: "none",
    },
    lightOn: {
        boxShadow: "0 0 15px",
    },
    red: {backgroundColor: "#FF4E4E"},
    yellow: {backgroundColor: "#FFDA65"},
    green: {backgroundColor: "#7ED957"},
    off: {backgroundColor: "#DDD"},
    reasonText: {
        marginTop: 16,
        color: "#fff",
        textAlign: "center",
        fontSize: 14,
    },
}));

type AmpelDisplayProps = {
    status: "green" | "yellow" | "red" | null;
    reason: string;
};

export const AmpelDisplay: React.FC = ({status, reason}: AmpelDisplayProps) => {
    const {classes, cx} = useAmpelStyles();

    const getLightClass = (color: "red" | "yellow" | "green") => {
        if (status === color) return cx(classes.light, classes.lightOn, classes[color]);
        return cx(classes.light, classes.off);
    };

    return (
        <Box className={classes.root}>
            <Box className={getLightClass("red")}/>
            <Box className={getLightClass("yellow")}/>
            <Box className={getLightClass("green")}/>
            {status && <Typography className={classes.reasonText}>{reason}</Typography>}
        </Box>
    );
};
