FROM python:3.10-slim

# Set workdir
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Run backend without reload (production)
CMD ["uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8000"]