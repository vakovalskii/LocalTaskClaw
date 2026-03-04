"""LocalClaw Core — entry point."""

import uvicorn
from config import CONFIG
from logger import core_logger
from db import init_db


def main():
    core_logger.info("=" * 50)
    core_logger.info("LocalClaw Core Agent")
    core_logger.info(f"  Model:     {CONFIG.model}")
    core_logger.info(f"  LLM URL:   {CONFIG.llm_base_url}")
    core_logger.info(f"  Workspace: {CONFIG.workspace}")
    core_logger.info(f"  Port:      {CONFIG.api_port}")
    core_logger.info("=" * 50)

    init_db()

    from api import app
    uvicorn.run(app, host="0.0.0.0", port=CONFIG.api_port, log_level="warning")


if __name__ == "__main__":
    main()
