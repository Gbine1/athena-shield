"""Compatible backend entry point: python server.py or uvicorn server:app."""
from api import app, main

if __name__ == "__main__":
    main()
