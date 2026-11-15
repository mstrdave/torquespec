"""FastAPI app: reference data endpoints plus a streaming diagnosis chat."""

from __future__ import annotations

import json
from importlib import resources
from typing import Literal

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import knowledge
from .diagnose import ChatTurn, Diagnoser, make_client


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class DiagnoseRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=40)

    @field_validator("messages")
    @classmethod
    def alternating(cls, v: list[Message]) -> list[Message]:
        if v[0].role != "user" or v[-1].role != "user":
            raise ValueError("conversation must start and end with a user message")
        if any(a.role == b.role for a, b in zip(v, v[1:], strict=False)):
            raise ValueError("roles must alternate")
        return v


def create_app(diagnoser: Diagnoser | None = None) -> FastAPI:
    kb = knowledge.load()
    diag = diagnoser or Diagnoser(kb, make_client())
    app = FastAPI(title="Torque Spec", version="0.1.0",
                  description="Diagnosis and specs for the 1990 Mazda MX-5 Miata")
    static = resources.files("torquespec").joinpath("static")
    app.mount("/static", StaticFiles(directory=str(static)), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(str(static.joinpath("index.html")))

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "llm": diag.available}

    @app.get("/api/vehicle")
    def vehicle() -> dict:
        return kb.vehicle

    @app.get("/api/torque")
    def torque(q: str = "") -> list[dict]:
        return [t.to_dict() for t in kb.search_torque(q)]

    @app.get("/api/codes")
    def codes() -> dict:
        return kb.codes

    @app.get("/api/codes/{code}")
    def code(code: str) -> dict:
        found = kb.lookup_code(code)
        if not found:
            raise HTTPException(404, f"Code {code} is not a known 1990 Miata flash code")
        return found

    @app.get("/api/issues")
    def issues() -> list[dict]:
        return list(kb.issues)

    @app.post("/api/diagnose")
    async def diagnose(req: DiagnoseRequest) -> StreamingResponse:
        if not diag.available:
            raise HTTPException(503, "Diagnosis needs ANTHROPIC_API_KEY set on the server.")
        turns = [ChatTurn(m.role, m.content) for m in req.messages]

        async def events():
            try:
                async for text in diag.stream(turns):
                    yield f"data: {json.dumps({'text': text})}\n\n"
            except anthropic.RateLimitError:
                yield f"data: {json.dumps({'error': 'Rate limited. Wait a moment and try again.'})}\n\n"
            except anthropic.APIStatusError as e:
                yield f"data: {json.dumps({'error': f'API error {e.status_code}.'})}\n\n"
            except anthropic.APIConnectionError:
                yield f"data: {json.dumps({'error': 'Could not reach the model. Check the connection.'})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return app


app = create_app()


def main() -> None:
    import uvicorn
    uvicorn.run("torquespec.app:app", host="127.0.0.1", port=8000)
