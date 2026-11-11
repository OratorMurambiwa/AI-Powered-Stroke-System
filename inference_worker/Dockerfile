FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
ENV USER=stroke-inference LOGNAME=stroke-inference TORCHINDUCTOR_CACHE_DIR=/tmp/torch PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 YOLO_CONFIG_DIR=/tmp/yolo MPLCONFIGDIR=/tmp/matplotlib OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 CUDA_VISIBLE_DEVICES=""
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY inference_worker/requirements.txt /tmp/requirements.txt
COPY inference_worker/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.txt -c /tmp/requirements.lock
WORKDIR /app
COPY inference_worker/child.py inference_worker/model.py inference_worker/probe.py inference_worker/server.py inference_worker/pool.py /app/inference_worker/
COPY inference_worker/tests/test_worker.py inference_worker/tests/test_ipc.py inference_worker/tests/test_transport.py /app/inference_worker/tests/
COPY inference_worker/README.md /app/inference_worker/
COPY clinical_api/png.py clinical_api/errors.py /app/clinical_api/
ENV YOLO_OFFLINE=true
USER 65532:65532
ENTRYPOINT ["python", "-m", "inference_worker.server"]
