import os
import logging
import sys

# Ensure the log directory exists
os.makedirs('.tmp', exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('.tmp/execution.log')
    ]
)

def get_logger(name):
    return logging.getLogger(name)

def ensure_directory(path):
    """Ensures a directory exists."""
    if not os.path.exists(path):
        os.makedirs(path)
        logging.info(f"Created directory: {path}")

# Example usage
if __name__ == "__main__":
    logger = get_logger("utils_test")
    logger.info("Utils module loaded successfully.")
