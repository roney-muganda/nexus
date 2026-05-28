import asyncio
import logging
import os
import sys

# Ensure the root directory is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from desktop_spoke.websocket import connect_to_hub

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

if __name__ == "__main__":
    try:
        # Run the agent's connection loop indefinitely
        asyncio.run(connect_to_hub())
    except KeyboardInterrupt:
        print("\nShutting down NEXUS Desktop Agent...")