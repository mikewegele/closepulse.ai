import React from "react";
import {Link} from "react-router-dom";
import {makeStyles} from "tss-react/mui";

const useStyles = makeStyles()(() => ({
    nav: {
        width: "100%",
        padding: "1rem 0rem",
        backgroundColor: "#FF6F61",
        display: "flex",
        justifyContent: "center",
        gap: "2rem",
        fontFamily: "'Helvetica Neue', Helvetica, Arial, sans-serif",
    },
    link: {
        color: "#fff",
        fontWeight: 600,
        fontSize: "1.1rem",
        textDecoration: "none",
        padding: "0.5rem 1rem",
        borderRadius: 30,
        transition: "background-color 0.3s ease",
        "&:hover": {
            backgroundColor: "rgba(255, 255, 255, 0.3)",
            textDecoration: "none",
            color: "#fff",
        },
    },
}));

const Header: React.FC = () => {
    const {classes} = useStyles();

    return (
        <nav className={classes.nav}>
            <Link className={classes.link} to="/">
                Voice Assistant
            </Link>
            <Link className={classes.link} to="/admin">
                Admin
            </Link>
        </nav>
    );
};

export default Header;
