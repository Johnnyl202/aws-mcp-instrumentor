from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
from client import CloudWatchAIAgent
from contextlib import contextmanager
from typing import Iterator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up FastAPI
app = FastAPI(title="CloudWatch AI Agent API")

# Request and response models
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

# Global agent instance
agent = None

@contextmanager
def get_agent() -> Iterator[CloudWatchAIAgent]:
    with CloudWatchAIAgent() as agent_manager:
        agent = agent_manager.start_session()
        yield agent

@app.get("/")
def root():
    return {"message": "CloudWatch AI Agent API is running"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        # Create a new agent for each request
        with get_agent() as agent:
            response = agent(request.message)
            return ChatResponse(response=str(response))
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
