import React from "react";
import {Box} from "@mui/material";
import {makeStyles} from "tss-react/mui";

const useAmpelStyles = makeStyles()(() => ({
    circle: {
        width: 24,
        height: 24,
        borderRadius: "50%",
        boxShadow: "0 0 8px rgba(0,0,0,0.3)",
        position: "absolute",
        top: 8,
        right: 8,
        transition: "background-color 0.3s ease",
    },
    red: {backgroundColor: "#FF4E4E"},
    yellow: {backgroundColor: "#FFDA65"},
    green: {backgroundColor: "#7ED957"},
    off: {backgroundColor: "#DDD"},
}));

export const AmpelSingleLight: React.FC<{ status: "green" | "yellow" | "red" | null }> = ({status}) => {
    const {classes, cx} = useAmpelStyles();

    let colorClass = classes.off;
    if (status === "red") colorClass = classes.red;
    else if (status === "yellow") colorClass = classes.yellow;
    else if (status === "green") colorClass = classes.green;

    return <Box className={cx(classes.circle, colorClass)}/>;
};