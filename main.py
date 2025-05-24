from fastapi import FastAPI, HTTPException

app = FastAPI()

@app.get("/generate-matrix")
def generate_matrix():
    try:
        # Простой тест — вернуть JSON, а не ZIP
        return {
            "status": "OK",
            "message": "Тест прошёл успешно",
            "data": [
                {"id": "a.a.01", "title": "Компетенция 1"},
                {"id": "a.a.02", "title": "Компетенция 2"}
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
