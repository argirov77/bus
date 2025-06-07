FROM python:3.12-slim

# install nodejs and npm
RUN apt-get update \ 
    && apt-get install -y nodejs npm \ 
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# build frontend
RUN cd frontend && npm install && npm run build && cd ..

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
