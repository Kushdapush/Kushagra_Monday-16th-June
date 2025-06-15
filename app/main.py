from fastapi import FastAPI
from app.api.endpoints import router
from app.models.database import engine, Base
import uvicorn

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Loop Store Monitoring API",
    description="API for monitoring store uptime and generating reports",
    version="1.0.0"
)

app.include_router(router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Loop Store Monitoring API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)