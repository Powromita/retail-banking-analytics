"""One command: generate data -> load SQLite -> analytics + model -> exports."""
from src import analytics, etl, generate_data

if __name__ == "__main__":
    generate_data.main()
    etl.main()
    analytics.main()
    print("\nDone. Start the dashboard with: uvicorn src.api:app --reload  ->  http://127.0.0.1:8000")
