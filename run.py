# run.py
# --- Make sure there is NO space before this line ---
from app import app # Import the app instance from our app package

# --- Make sure there is NO space before this line ---
if __name__ == '__main__':
    # --- Make sure this line is indented correctly (usually 4 spaces) ---
    # Runs the Flask development server
    # Set debug back to True for development
    print("--- Starting Flask server with debug=True ---")
    app.run(debug=True)
