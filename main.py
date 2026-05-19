from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from chatbot import laad_handleidingen, genereer_antwoord

app = FastAPI(title="HandleidingChat")
handleidingen = laad_handleidingen()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/handleidingen", StaticFiles(directory="handleidingen"), name="handleidingen-bestanden")


class Bericht(BaseModel):
    tekst: str
    filter: list[str] | None = None


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.post("/chat")
def chat(bericht: Bericht):
    return genereer_antwoord(bericht.tekst, handleidingen, filter_namen=bericht.filter or None)


@app.get("/handleidingen-lijst")
def lijst_handleidingen():
    return {
        "handleidingen": [
            {"naam": naam, "aantal_secties": len(secties)}
            for naam, secties in handleidingen.items()
        ]
    }
