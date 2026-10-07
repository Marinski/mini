# Throwaway sandbox for the HumanEval suite: stdlib Python, no network.
# Build with: python -c "from bench import humaneval; humaneval.build_image()"
FROM python:3.12-slim

RUN useradd --create-home sandbox
USER sandbox
WORKDIR /problem
ENV PYTHONDONTWRITEBYTECODE=1
