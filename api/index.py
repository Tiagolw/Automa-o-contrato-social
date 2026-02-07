from flask import Flask, render_template, request, send_file, redirect, url_for, session
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the Flask app from the main app.py
from app import app

# Vercel requires the app to be exposed as 'app'
# The app variable is already imported from app.py
