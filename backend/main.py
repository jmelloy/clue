from app.logging import get_logging_config

if __name__ == "__main__":
    import uvicorn
    import os

    debug = os.getenv("DEBUG", "false").lower() == "true"
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging_config = get_logging_config(log_level=log_level, log_format="colored")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=debug,
        log_config=logging_config,
    )
