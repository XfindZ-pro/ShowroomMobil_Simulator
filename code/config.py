import os

# PATH SYSTEM
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SYSTEM_DIR = os.path.join(BASE_DIR, "system")

# FILE PATHS
DB_FILE = os.path.join(DATA_DIR, "firzanta_motor.db")
RULES_FILE = os.path.join(SYSTEM_DIR, "peraturan.md")

# AI CONFIG
MODEL_NAME = "deepseek-r1:8b" 

# GAME SETTINGS
PROFIT_MARGIN_MIN = 0.05 
PROFIT_MARGIN_TARGET = 0.15