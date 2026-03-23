from fastapi import FastAPI
from .routes import runs

app = FastAPI()

app.include_router(runs.router)

@app.get("/")
def read_root():
    return {"Hello": "World"}

# WebSocket endpoint will be added here later

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
