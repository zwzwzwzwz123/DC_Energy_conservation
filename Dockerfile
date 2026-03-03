FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    MPLBACKEND=Agg \
    TZ=Asia/Shanghai

WORKDIR /app

# Runtime/system libraries:
# - libgomp1: for lightgbm/xgboost OpenMP
# - libgl1/libx*: for matplotlib backend dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1 \
    fonts-noto-cjk \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Install Linux-safe dependencies used by the full project (including generated pipelines).
COPY requirements.linux.txt /tmp/requirements.linux.txt
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r /tmp/requirements.linux.txt

COPY . /app

# Default entry keeps full project behavior.
# For generated scripts, override command in `docker run`.
CMD ["python", "DC_Energy_conservation/main.py"]
