# 📋 Sistema de Automação de Contrato Social

Sistema inteligente para geração automática de Contratos Sociais de Sociedade Limitada, utilizando Inteligência Artificial para extração de dados de documentos.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## ✨ Funcionalidades

- **Extração Inteligente**: Utiliza Mistral AI e OpenAI para extrair dados de documentos
- **Suporte a Múltiplos Formatos**: PDFs, imagens (JPG, PNG) e documentos escaneados
- **OCR Avançado**: Conversão automática de PDFs baseados em imagem para extração via Vision API
- **Múltiplos Sócios**: Suporte para 1 a 10 sócios por contrato
- **Geração DOCX**: Contratos gerados em formato Word editável
- **Interface Moderna**: Design responsivo e intuitivo

## 🚀 Como Usar

### 1. Instalação

```bash
# Clone o repositório
git clone https://github.com/Tiagolw/Automa-o-contrato-social.git
cd Automa-o-contrato-social

# Crie um ambiente virtual
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Instale as dependências
pip install -r requirements.txt
```

### 2. Configuração

Crie um arquivo `.env` na raiz do projeto:

```env
OPENAI_API_KEY=sua_chave_openai_aqui
MISTRAL_API_KEY=sua_chave_mistral_aqui
SECRET_KEY=uma_chave_secreta_qualquer
```

> 💡 **Dica**: O Mistral AI é priorizado para extração de texto (gratuito). OpenAI é usado para imagens/OCR.

### 3. Execução

```bash
python app.py
```

Acesse: **http://127.0.0.1:5000**

## 📁 Estrutura do Projeto

```
├── app.py                    # Aplicação Flask principal
├── contract_template.docx    # Template do contrato
├── requirements.txt          # Dependências Python
├── .env                      # Variáveis de ambiente (não versionado)
├── execution/
│   └── create_template.py    # Script para gerar o template
├── templates/
│   ├── landing.html          # Página inicial
│   ├── upload.html           # Upload de documentos
│   ├── form.html             # Formulário de revisão
│   └── download.html         # Download do contrato
├── static/
│   └── style.css             # Estilos CSS
└── .tmp/                     # Arquivos temporários (não versionado)
```

## 🔄 Fluxo de Uso

1. **Início**: Selecione o número de sócios
2. **Upload**: Envie documentos de identidade (RG, CNH, CIN) e da empresa (CNPJ)
3. **Revisão**: Verifique e edite os dados extraídos automaticamente
4. **Download**: Baixe o contrato social em formato Word

## 🤖 Tecnologias de IA

| Tipo de Documento | Tecnologia Usada |
|-------------------|------------------|
| PDF com texto (CNPJ) | Mistral AI (gratuito) |
| PDF escaneado (RG/CNH) | OpenAI Vision |
| Imagens (JPG/PNG) | OpenAI Vision |

## 📦 Dependências Principais

- **Flask** - Framework web
- **OpenAI** - API de IA para extração
- **Mistral AI** - API alternativa (gratuita)
- **PyMuPDF** - Conversão de PDF para imagem
- **python-docx / docxtpl** - Geração de documentos Word

## 🛠️ Desenvolvimento

### Regenerar o Template do Contrato

```bash
python execution/create_template.py
```

### Executar em Modo Debug

```bash
python app.py
# O servidor reinicia automaticamente quando você salva alterações
```

## 📄 Licença

Este projeto está licenciado sob a licença MIT.

## 👨‍💻 Autor

Desenvolvido por **Tiago Leite Wang**

---

⭐ Se este projeto foi útil, considere dar uma estrela no repositório!
