from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import uuid

app = FastAPI()

# Simple in-memory session store for demo/testing
SESSIONS: Dict[str, Dict[str, Any]] = {}

class StartRequest(BaseModel):
    problem_db_id: int = None

class StartResponse(BaseModel):
    session_id: str
    state: Dict[str, Any]

class StepRequest(BaseModel):
    session_id: str
    action: Dict[str, Any]

class StateResponse(BaseModel):
    session_id: str
    state: Dict[str, Any]

@app.post('/start', response_model=StartResponse)
async def start(req: StartRequest):
    # Create a session and populate a minimal initial state.
    session_id = str(uuid.uuid4())
    state = {
        'problem_db_id': req.problem_db_id,
        'phase': 'initialized',
        'representative_solutions': [],
        'preferred_solutions': [],
    }
    SESSIONS[session_id] = state
    return {'session_id': session_id, 'state': state}

@app.post('/step', response_model=StateResponse)
async def step(req: StepRequest):
    sid = req.session_id
    if sid not in SESSIONS:
        raise HTTPException(status_code=404, detail='session not found')
    # For demo purposes, accept an action and append it to state log
    state = SESSIONS[sid]
    actions = state.setdefault('actions', [])
    actions.append(req.action)
    # fake an update: record that step advanced
    state['phase'] = 'running'
    # if action requests solutions, return fake representative set
    if req.action.get('type') == 'get_representative_solutions':
        state['representative_solutions'] = [
            {'id': 1, 'vars': ["cpu1","gpu1"], 'objectives': [500, -3, -8]},
            {'id': 2, 'vars': ["cpu2","gpu2"], 'objectives': [800, -6, -12]}
        ]
    return {'session_id': sid, 'state': state}

@app.get('/state/{session_id}', response_model=StateResponse)
async def get_state(session_id: str):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail='session not found')
    return {'session_id': session_id, 'state': SESSIONS[session_id]}
