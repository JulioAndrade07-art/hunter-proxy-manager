#!/usr/bin/env python3
"""
app.py — Ponto de entrada do ProxyHunter
Responsável apenas por: criar o app Flask, registrar blueprints e iniciar servidor
"""

import logging
from flask import Flask
from routes import bp

# ---------------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------------
def create_app() -> Flask:
    """Factory de aplicação Flask. Permite testes unitários via import."""
    app = Flask(__name__)
    app.register_blueprint(bp)
    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Nível de log global (altere para logging.DEBUG para output mais verboso)
    logging.basicConfig(level=logging.INFO)

    app = create_app()
    print("\n🔥  ProxyHunter iniciado em  http://localhost:5000\n")
    app.run(debug=False, threaded=True, port=5000)
