"""
FastAPI Application - Main Entry Point

This is the main API server that orchestrates the 7-component pipeline.
"""

from fastapi import FastAPI

app = FastAPI(title="Text-to-SQL Chatbot API")

@app.get("/")
def root():
    return {"message": "Text-to-SQL Chatbot API"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "1.0.0"}

# TODO: Add /query endpoint
