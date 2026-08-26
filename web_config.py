"""
Local, PRIVATE configuration - keeps your Google Maps API key out of the
shared code. This file is listed in .gitignore so it is never pushed or
exported. If you share the project, DELETE your key from here first.

You can also override the key with an environment variable:
    setx GOOGLE_MAPS_API_KEY "your-key"     (Windows, new terminal after)
"""
import os

# Your Google Maps JavaScript API key.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# Port the Flask app runs on (must match your key's referrer restriction).
PORT = 8000
