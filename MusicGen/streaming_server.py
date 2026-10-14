import asyncio
import json
import logging
import multiprocessing as mp
import time
from typing import Any, Dict

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()
logger = logging.getLogger("streaming_server")
logging.basicConfig(level=logging.INFO)


class ModelWorker(mp.Process):
    """長寿命ワーカープロセス。モデルをロードしてジョブキューを待ち受ける。

    実運用ではここでStable Audioモデルをロード（FP16/GPU）し、要求ごとに
    短尺セグメント（例:5秒）を逐次生成して、レスポンスキューへputする。
    """

    def __init__(self, job_queue: mp.Queue):
        super().__init__(daemon=True)
        self.job_queue = job_queue

    def warmup(self):
        # ここでモデルロードとウォームアップ推論を行う（ダミー入力）
        logger.info("ModelWorker: loading model and warming up (simulated)")
        time.sleep(1.0)  # 実装ではモデルのロード時間
        logger.info("ModelWorker: warmup done")

    def generate_simulated(self, length_seconds: float, sample_rate: int, channels: int, segment_seconds: float):
        """実装例: Stable Audio の代わりにサイン波/ホワイトノイズを返す（デモ用）。

        実運用ではここをモデルの推論ループに置き換え、各セグメント完成時に
        response_queue.put({'pcm': bytes, 'segment_idx': i, 'timings': {...}}) とする。
        """
        total_frames = int(length_seconds * sample_rate)
        segment_frames = int(segment_seconds * sample_rate)
        produced = 0
        idx = 0
        while produced < total_frames:
            frames = min(segment_frames, total_frames - produced)
            t0 = time.time()
            # シンプルなサイン波（チャンネル分複製）
            t = (np.arange(frames) + produced) / sample_rate
            freq = 220.0 + 10.0 * idx
            seg = 0.1 * np.sin(2 * np.pi * freq * t, dtype=np.float32)
            if channels == 2:
                seg = np.stack([seg, seg], axis=1)
            # シミュレーション遅延（モデル推論時間）
            time.sleep(0.2 + 0.05 * idx)
            t1 = time.time()
            timings = {"gen_time": t1 - t0}
            # バイナリ化（Float32 PCM）
            pcm = seg.astype(np.float32).tobytes()
            yield {"pcm": pcm, "segment_idx": idx, "timings": timings}
            produced += frames
            idx += 1

    def run(self):
        self.warmup()
        while True:
            job = self.job_queue.get()
            if job is None:
                logger.info("ModelWorker: shutting down")
                break
            job_id = job.get("id")
            params = job.get("params")
            response_queue: mp.Queue = job.get("response_queue")
            logger.info(f"ModelWorker: received job {job_id} params={params}")
            try:
                # 実運用: ここでStable Audio生成ルーチンを呼ぶ
                length_seconds = float(params.get("length_seconds", 30.0))
                sample_rate = int(params.get("sample_rate", 44100))
                channels = int(params.get("channels", 2))
                segment_seconds = float(params.get("segment_seconds", 5.0))

                start_all = time.time()
                for seg in self.generate_simulated(length_seconds, sample_rate, channels, segment_seconds):
                    response_queue.put({"ok": True, "payload": seg})
                end_all = time.time()
                response_queue.put({"ok": True, "payload": None, "meta": {"total_time": end_all - start_all}})
            except Exception as e:
                logger.exception("ModelWorker: error during generation")
                response_queue.put({"ok": False, "error": str(e)})


# グローバルなジョブキューとワーカー（アプリ起動時に作る）
manager_job_queue: mp.Queue = mp.Queue()
worker: ModelWorker = None


@app.on_event("startup")
def startup_event():
    global worker, manager_job_queue
    logger.info("Starting ModelWorker process...")
    worker = ModelWorker(manager_job_queue)
    worker.start()


@app.on_event("shutdown")
def shutdown_event():
    global worker, manager_job_queue
    logger.info("Stopping ModelWorker process...")
    try:
        manager_job_queue.put(None)
    except Exception:
        pass
    if worker is not None:
        worker.join(timeout=5.0)


@app.get("/")
def index():
    html = """
    <html><body>
    <h2>Streaming server</h2>
    <p>Use the client demo to connect.</p>
    </body></html>
    """
    return HTMLResponse(content=html)


@app.websocket("/generate/ws")
async def generate_ws(websocket: WebSocket):
    await websocket.accept()
    job_id = int(time.time() * 1000)
    try:
        # 期待: クライアントがJSONでパラメータを送る
        data = await websocket.receive_text()
        params = json.loads(data)
        logger.info(f"WS {job_id}: params={params}")

        response_queue = mp.Queue()
        manager_job_queue.put({"id": job_id, "params": params, "response_queue": response_queue})

        # 送信先のPCMフォーマットを先に通知
        sample_rate = int(params.get("sample_rate", 44100))
        channels = int(params.get("channels", 2))
        await websocket.send_text(json.dumps({"type": "format", "sample_rate": sample_rate, "channels": channels, "dtype": "float32"}))

        # 非同期にレスポンスキューを監視してクライアントへ送る
        loop = asyncio.get_event_loop()
        start_time = time.time()
        while True:
            # blockingなQueue.getをスレッドに任せて待つ
            item = await loop.run_in_executor(None, response_queue.get)
            if item is None:
                break
            if not item.get("ok", False):
                await websocket.send_text(json.dumps({"type": "error", "msg": item.get("error")}))
                break
            payload = item.get("payload")
            if payload is None:
                # 終了メタ情報
                await websocket.send_text(json.dumps({"type": "end", "meta": item.get("meta")}))
                break
            seg = payload
            # まずタイミングをログ
            logger.info(f"WS {job_id}: sending segment {seg['segment_idx']} gen_time={seg['timings']['gen_time']:.3f}s")
            # 送信: バイナリフレームでRaw PCMを送る
            await websocket.send_bytes(seg["pcm"])

        total = time.time() - start_time
        logger.info(f"WS {job_id}: finished stream total_time={total:.3f}s")
    except WebSocketDisconnect:
        logger.info(f"WS {job_id}: client disconnected")
    except Exception:
        logger.exception("WS handling error")
    finally:
        try:
            response_queue.close()
        except Exception:
            pass
