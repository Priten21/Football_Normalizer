from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json

from mapper import map_api_to_json, assess_mapping_quality
from chat import ask_football_question
from evaluate_accuracy import run_evaluation

app = FastAPI(title="Football Normalizer API")

class MapRequest(BaseModel):
    raw_data: str

class ChatRequest(BaseModel):
    question: str
    match_data: dict

@app.post("/api/map")
async def api_map(req: MapRequest):
    try:
        # Pass the raw string to the model mapping function
        mapped_dict = map_api_to_json(req.raw_data)
        quality = assess_mapping_quality(mapped_dict)
        return {
            "type": mapped_dict.get("type"),
            "data": mapped_dict.get("data"),
            "field_confidences": mapped_dict.get("field_confidences"),
            "mapping_trace": mapped_dict.get("mapping_trace"),
            "quality": quality
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    try:
        # Chat needs context as a string. Serialize the dictionary back to string.
        response_text = ask_football_question(req.question, json.dumps(req.match_data))
        return {"answer": response_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/accuracy")
async def api_accuracy():
    try:
        results = run_evaluation()
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files for the frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
