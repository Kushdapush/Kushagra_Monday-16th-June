from fastapi import FastAPI
from app.api.endpoints import router
from app.models.database import engine, Base
import uvicorn

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Store Monitoring API",
    description="API for store uptime reports",
    version="1.0.0"
)

app.include_router(router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Store Monitoring API - Working!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)