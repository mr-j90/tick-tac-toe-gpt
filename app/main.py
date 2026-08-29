from fastapi import FastAPI

app = FastAPI(title="tic-tac-toe")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
