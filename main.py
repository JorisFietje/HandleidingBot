from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from chatbot import laad_handleidingen, genereer_antwoord

app = FastAPI(title="HandleidingChat")
handleidingen = laad_handleidingen()

app.mount("/static", StaticFiles(directory="static"), name="static")


class Bericht(BaseModel):
    tekst: str


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.post("/chat")
def chat(bericht: Bericht):
    antwoord = genereer_antwoord(bericht.tekst, handleidingen)
    return antwoord


@app.get("/handleidingen")
def lijst_handleidingen():
    return {
        "handleidingen": [
            {"naam": naam, "secties": [s.titel for s in secties]}
            for naam, secties in handleidingen.items()
        ]
    }
