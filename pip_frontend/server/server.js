const express = require("express");
const multer = require("multer");
const app = express();
const upload = multer();

app.use(express.json());

const BOOK = {
    "+4930123456": {name: "Muster GmbH", phone: "+4930123456"},
    "+4915122233344": {name: "Anna Beispiel", phone: "+4915122233344"}
};

app.get("/customer", (req, res) => {
    const p = (req.query.phone || "").trim();
    res.json(BOOK[p] || {name: "Unbekannt", phone: p});
});

app.post("/trafficLight", (req, res) => res.json({response: "green"}));

app.post("/transcribe", upload.single("file"), (req, res) =>
    res.json({text: "Kunde fragt nach Lieferstatus 12345."})
);

app.post("/ask", (req, res) =>
    res.json({
        response:
            "- Zusammenfassung: Kunde fragt nach Bestellung 12345.\n" +
            "- Nächste Schritte: Status prüfen, Rückruf.\n" +
            "- Tag: Logistik\n"
    })
);

app.listen(8000, () => console.log("Mock-API on http://localhost:8000"));
