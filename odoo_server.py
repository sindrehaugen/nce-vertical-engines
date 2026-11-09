"""
Standalone Super-Intelligent Odoo + LLM Cross-Talker Server Entry Point.
Run with: `uvicorn odoo_server:app --host 0.0.0.0 --port 8093`
"""

from nce_verticals.odoo.app import create_standalone_odoo_app

app = create_standalone_odoo_app()
