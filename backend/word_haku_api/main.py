import os
import torch
# Limit CPU threads used by native libraries to avoid saturating the host
# (prevents heavy inference from starving other components like Bluetooth handling)
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
try:
    torch.set_num_threads(1)
except Exception:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from word_haku_api.routers.route_eeg_emotion import router as route_eeg_emotion
from word_haku_api.routers.route_music import router as route_music
from word_haku_api.routers.route_experiment import router as route_experiment
from decouple import config

app = FastAPI()
FRONTEND_URL = config('FRONTEND_URL')

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],  # ReactからのAPIアクセスを許可
    allow_credentials=True,
    allow_methods=["*"],  # 全てのHTTPメソッドを許可
    allow_headers=["*"],  # 全てのHTTPヘッダーを許可
)

app.include_router(route_eeg_emotion, prefix="/eeg_emotion", tags=["eeg_emotion"])
app.include_router(route_music, prefix="/music", tags=["music"])
app.include_router(route_experiment, prefix="/experiment", tags=["experiment"])


@app.get("/")
def root():
    return {"message": "Welcome to word-haku-API"}