from fastapi import FastAPI, Request
from fastapi.responses import Response
from proxy import forward_to_gonic

app = FastAPI(title="sonyaproxy")

@app.api_route("/rest/{path:path}", methods=["GET", "POST"])
async def subsonic_proxy(request: Request, path: str) -> Response:
    return await forward_to_gonic(request)
