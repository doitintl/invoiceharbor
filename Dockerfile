# Use an official Python runtime as a parent image
FROM python:3.12-slim-bullseye as builder

# Set environment varibles
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /code

# Install python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt

##################
# FINAL IMAGE
##################
FROM python:3.12-slim-bullseye

# Create app directory
WORKDIR /app

# Create a non-root user and group
RUN groupadd --system appgroup && useradd --system --gid appgroup appuser

# Install dependencies
COPY --from=builder /wheels /wheels
COPY --from=builder /code/requirements.txt .
RUN pip install --no-cache-dir /wheels/*

# Copy main app
COPY main.py .

# Change ownership of the app directory
RUN chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Set the entrypoint to the Python script
ENTRYPOINT ["python", "./main.py"]