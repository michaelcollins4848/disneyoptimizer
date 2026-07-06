from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import rides, shows, plans

app = FastAPI(title="DisneyLine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rides.router, prefix="/api")
app.include_router(shows.router, prefix="/api")
app.include_router(plans.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
