"""
Standalone Salesforce + Entra ID Vertical Engine Server Entry Point.
Run with: `uvicorn salesforce_server:app --host 0.0.0.0 --port 8092`
"""

from nce_verticals.salesforce.app import create_standalone_salesforce_app

app = create_standalone_salesforce_app()
