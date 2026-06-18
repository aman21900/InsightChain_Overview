# Importing requirements
from ui import app
from startup import initialize

if __name__ == "__main__":
    initialize()
    app.launch(
        favicon_path="assets/InsightChain_logo_cropped-removebg-preview.ico"
    )