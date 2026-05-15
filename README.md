# ProxyHunter 🔍

🗣️ *[Read in English](#english-version)* | 🇧🇷 *[Ler em Português](#versão-em-português)*

---

## 🇧🇷 Versão em Português

> **Sistema avançado de busca, validação e criação de proxies — sem dependências pesadas.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey?logo=flask)
![License](https://img.shields.io/badge/license-MIT-green)

### ✨ Funcionalidades

| Feature | Detalhes |
|---|---|
| **Scan Paralelo** | Coleta proxies de 6 fontes em paralelo e testa com 40 threads simultâneas via SSE |
| **Proxy HTTP/HTTPS** | Servidor local com suporte a CONNECT tunnel (HTTPS) e autenticação Basic |
| **Proxy SOCKS5** | Servidor asyncio com autenticação RFC 1929 e graceful shutdown |
| **Multi-instância** | Crie quantas proxies locais quiser em portas independentes |
| **Logs em tempo real** | SSE por instância — visualize o tráfego à medida que acontece |
| **Exportação** | TXT / JSON / CSV + formato BOT (`IP:PORTA:USER:PASS`) |

### 🗂 Estrutura do Projeto

```text
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
```

### 🚀 Instalação e Uso

```bash
# Clone o repositório
git clone https://github.com/JulioAndrade07-art/hunter-proxy-manager.git
cd hunter-proxy-manager

# Instale os requisitos
pip install -r requirements.txt

# Inicie o servidor
python app.py
```
Acesse: **http://localhost:5000**

---

<br><br>

## 🇺🇸 English Version

> **Advanced scanning, validation, and proxy creation system — lightweight and dependency-free.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey?logo=flask)
![License](https://img.shields.io/badge/license-MIT-green)

### ✨ Features

| Feature | Details |
|---|---|
| **Parallel Scan** | Scrapes proxies from 6 sources concurrently and tests via 40 threads using SSE |
| **HTTP/HTTPS Proxy** | Local server featuring CONNECT tunneling (HTTPS) & Basic Auth |
| **SOCKS5 Proxy** | Custom asyncio server with RFC 1929 Auth & graceful shutdown |
| **Multi-instance** | Launch as many local proxies as you want on independent ports |
| **Real-time Logs** | SSE-powered realtime traffic visualization per instance |
| **Mass Export** | TXT / JSON / CSV + Antidetect BOT format (`IP:PORT:USER:PASS`) |

### 🚀 Installation & Usage

```bash
# Clone the repository
git clone https://github.com/JulioAndrade07-art/hunter-proxy-manager.git
cd hunter-proxy-manager

# Intall the requirements
pip install -r requirements.txt

# Start the server
python app.py
```
Open: **http://localhost:5000**

### 🔌 Using as a Local Proxy

**HTTP / HTTPS**
```bash
curl -x http://YOUR_LAN_IP:8080 http://httpbin.org/ip
```

**SOCKS5**
```bash
curl -x socks5://YOUR_LAN_IP:1080 http://httpbin.org/ip
```

**With Authentication**
```bash
curl -x http://user:pass@YOUR_LAN_IP:8080 http://httpbin.org/ip
```

---
### 📄 License
MIT © 2025
