# 📋 Automação de Contrato Social

Sistema de automação para geração de Contratos Sociais de empresas, com extração automática de dados de documentos usando Inteligência Artificial.

## ✨ Funcionalidades

- **📤 Upload de Documentos:** Envie RG, CNH, CIN e comprovantes de endereço
- **🤖 Extração com IA:** Leitura automática de dados usando OpenAI GPT-4o e Mistral AI
- **📝 Formulário Inteligente:** Campos pré-preenchidos com dados extraídos
- **📄 Geração de DOCX:** Criação automática do contrato no formato Word
- **📊 Dashboard:** Visualize, edite e gerencie todos os contratos
- **💾 Persistência:** Dados salvos no Supabase com histórico completo
- **🔄 Rascunhos Automáticos:** Nunca perca seu progresso

---

## 🚀 Instalação

### Pré-requisitos

- Python 3.10+
- Conta no [Supabase](https://supabase.com) (gratuito)
- Chave de API da [OpenAI](https://platform.openai.com) (obrigatório)
- Chave de API da [Mistral AI](https://mistral.ai) (opcional, melhora performance)

### 1. Clone o Repositório

```powershell
git clone <url-do-repositorio>
cd "Automação contrato social"
```

### 2. Crie o Ambiente Virtual

```powershell
python -m venv .venv
```

### 3. Ative o Ambiente Virtual

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
.venv\Scripts\activate.bat
```

**Linux/macOS:**
```bash
source .venv/bin/activate
```

### 4. Instale as Dependências

```powershell
pip install -r requirements.txt
```

### 5. Configure as Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
# Supabase (obrigatório para persistência)
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_KEY=sua_chave_publica

# OpenAI (obrigatório para extração de documentos)
OPENAI_API_KEY=sk-proj-sua-chave-aqui

# Mistral AI (opcional, melhora extração de PDFs)
MISTRAL_API_KEY=sua_chave_mistral

# Flask (opcional)
SECRET_KEY=uma_chave_secreta_qualquer
```

---

## ▶️ Executando o Servidor

### Iniciar o Servidor (Desenvolvimento)

```powershell
python app.py
```

O servidor estará disponível em: **http://127.0.0.1:5000**

### Iniciar o Servidor (Produção com Gunicorn)

```bash
gunicorn app:app --bind 0.0.0.0:8000
```

---

## ⏹️ Parando o Servidor

### Opção 1: No Terminal Ativo

Pressione `Ctrl + C` no terminal onde o servidor está rodando.

### Opção 2: Forçar Parada (PowerShell)

```powershell
Stop-Process -Name python -Force
```

### Opção 3: Forçar Parada (CMD/Windows)

```cmd
taskkill /F /IM python.exe
```

### Opção 4: Reiniciar Servidor (Parar e Iniciar)

```powershell
Stop-Process -Name python -Force; Start-Sleep -Seconds 2; python app.py
```

---

## 📁 Estrutura do Projeto

```
├── app.py                    # Aplicação principal Flask
├── requirements.txt          # Dependências Python
├── contract_template.docx    # Template do contrato Word
├── .env                      # Variáveis de ambiente (não versionado)
│
├── templates/                # Templates HTML (Jinja2)
│   ├── dashboard.html        # Página principal com lista de contratos
│   ├── upload.html           # Página de upload de documentos
│   ├── form.html             # Formulário de edição de dados
│   ├── download.html         # Página de download do contrato
│   └── config.html           # Página de configurações
│
├── static/                   # Arquivos estáticos
│   └── style.css             # Estilos CSS
│
└── .tmp/                     # Arquivos temporários (uploads, gerados)
```

---

## 🔧 Configuração do Supabase

1. Crie um projeto no [Supabase](https://supabase.com)
2. Execute o seguinte SQL no Editor SQL do Supabase:

```sql
CREATE TABLE IF NOT EXISTS contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    name TEXT,
    status TEXT DEFAULT 'draft',
    partners JSONB DEFAULT '[]'::jsonb,
    company_data JSONB DEFAULT '{}'::jsonb
);

ALTER TABLE contracts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Enable all access for anon users" ON contracts
FOR ALL TO anon USING (true) WITH CHECK (true);
```

---

## 📖 Como Usar

1. **Acesse o Dashboard** em http://127.0.0.1:5000
2. **Clique em "Novo Contrato"** e selecione o número de sócios
3. **Faça upload dos documentos:**
   - RG, CNH ou CIN de cada sócio
   - Comprovante de endereço (conta de luz, água, etc.)
   - Documentos da empresa (CNPJ, contrato anterior)
4. **Revise os dados** extraídos automaticamente no formulário
5. **Clique em "Gerar Contrato"** para criar o documento Word
6. **Baixe o arquivo** e pronto!

---

## 🐛 Solução de Problemas

| Problema | Solução |
|----------|---------|
| `ModuleNotFoundError: No module named 'flask'` | Execute `pip install -r requirements.txt` |
| Documentos não são lidos | Verifique se `OPENAI_API_KEY` está no `.env` |
| Dashboard vazio | Verifique se `SUPABASE_URL` e `SUPABASE_KEY` estão corretos |
| Erro ao gerar contrato | Verifique se `contract_template.docx` existe na raiz |

---

## 📄 Licença

Este projeto é de uso interno da Madruga Contabilidade.

---

## 👨‍💻 Desenvolvido com

- [Flask](https://flask.palletsprojects.com/) - Framework Web Python
- [OpenAI GPT-4o](https://openai.com) - Extração de dados com IA
- [Mistral AI](https://mistral.ai) - OCR e parsing de documentos
- [Supabase](https://supabase.com) - Banco de dados PostgreSQL
- [python-docx](https://python-docx.readthedocs.io/) - Geração de documentos Word
