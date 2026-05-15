# ProxyHunter 🔍

> **Sistema avançado de busca, validação e criação de proxies — sem dependências pesadas.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey?logo=flask)
![License](https://img.shields.io/badge/license-MIT-green)

---

## ✨ Funcionalidades

| Feature | Detalhes |
|---|---|
| **Scan Paralelo** | Coleta proxies de 6 fontes em paralelo e testa com 40 threads simultâneas via SSE |
| **Proxy HTTP/HTTPS** | Servidor local com suporte a CONNECT tunnel (HTTPS) e autenticação Basic |
| **Proxy SOCKS5** | Servidor asyncio com autenticação RFC 1929 e graceful shutdown |
| **Multi-instância** | Crie quantas proxies locais quiser em portas independentes |
| **Logs em tempo real** | SSE por instância — visualize o tráfego à medida que acontece |
| **Exportação** | TXT / JSON / CSV + formato BOT (`IP:PORTA:USER:PASS`) |

---

## 🗂 Estrutura do Projeto

```
proxy_system/
├── app.py           # Entry point — Flask factory
├── routes.py        # Todos os endpoints REST e SSE (Blueprint)
├── proxy_server.py  # Motor HTTP/SOCKS5, relay, autenticação
├── scrapers.py      # Scrapers multi-thread + deduplicação
├── utils.py         # Logger, IP local, helpers
│
├── templates/
│   └── index.html   # HTML semântico limpo
│
├── static/
│   ├── css/style.css          # Design System completo
│   └── js/
│       ├── main.js            # Scanner UI + SSE + Exportação
│       └── proxy_manager.js   # Gerenciador de proxies locais
│
├── requirements.txt
└── .gitignore
```

---

## 🚀 Instalação e Uso

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/proxyhunter.git
cd proxyhunter

# 2. Crie um ambiente virtual (recomendado)
python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\Scripts\activate      # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Execute
python app.py
```

Acesse: **http://localhost:5000**

---

## 🔌 Uso como Proxy Local

### HTTP / HTTPS
```bash
curl -x http://SEU_IP:8080 http://httpbin.org/ip
```

### SOCKS5
```bash
curl -x socks5://SEU_IP:1080 http://httpbin.org/ip
```

### Com autenticação
```bash
curl -x http://usuario:senha@SEU_IP:8080 http://httpbin.org/ip
```

---

## 🛠 Requisitos

- Python **3.10+**
- `flask >= 3.0`
- `requests >= 2.32`
- Tudo o mais é **biblioteca padrão do Python** (asyncio, threading, socket, http.server…)

---

## 📄 Licença

MIT © 2025
