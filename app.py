from flask import Flask, render_template, request, send_file, redirect, url_for, jsonify, flash
import os
import re
import base64
import json
import traceback
import gc
import io
import pypdf
from PIL import Image
from docxtpl import DocxTemplate
from openai import OpenAI
from dotenv import load_dotenv
import time

# Optional imports for PDF to image conversion
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    convert_from_path = None  # type: ignore
    PDF2IMAGE_AVAILABLE = False

# Enable PyMuPDF - Safe due to sequential processing
try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    fitz = None  # type: ignore
    FITZ_AVAILABLE = False

load_dotenv()

# Get the directory where app.py is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, 
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))

# Use /tmp for serverless environments (Vercel), .tmp for local
if os.environ.get('VERCEL'):
    app.config['UPLOAD_FOLDER'] = '/tmp'
else:
    app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, '.tmp')
    
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_very_secret')

# Ensure tmp folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# OpenAI Client
openai_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_key) if openai_key else None

# Mistral AI Client
mistral_key = os.getenv("MISTRAL_API_KEY")
mistral_client = None
if mistral_key:
    try:
        from mistralai import Mistral
        mistral_client = Mistral(api_key=mistral_key)
        print("[INFO] Mistral AI client initialized")
    except Exception as e:
        print(f"[WARN] Could not initialize Mistral: {e}")

# Supabase Client
supabase_client = None
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
if supabase_url and supabase_key:
    try:
        from supabase import create_client, Client
        supabase_client: Client = create_client(supabase_url, supabase_key)
        print("[INFO] Supabase client initialized")
    except Exception as e:
        print(f"[WARN] Could not initialize Supabase: {e}")


def extract_text_from_pdf(filepath):
    try:
        reader = pypdf.PdfReader(filepath)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF {filepath}: {e}")
        return ""

def extract_data_with_ai(text):
    if not openai_client or not text:
        return {}
    
    prompt = """
    Extract data from the provided text for a "Contrato Social". 
    Return a JSON object with keys: 
    - name (Full Name)
    - nationality
    - civil_state
    - regime (if married)
    - profession
    - birth_date
    - cpf
    - address (Full address including CEP)
    
    If it's a company document, extract:
    - company_name
    - company_address
    - company_object
    - company_cnae_list
    - start_date
    - capital_currency
    - total_quotas
    - quota_value
    - forum_city

    Return minimal valid JSON.
    """
    
    try:
        assert openai_client is not None  # Already checked above
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a legal assistant."},
                {"role": "user", "content": f"{prompt}\n\nText:\n{text[:15000]}"}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON from AI: {e}")
        return {}
    except Exception as e:
        print(f"[ERROR] AI Extraction Error: {e}")
        return {}

def compress_image_for_api(filepath, max_size_kb=1024, max_dimension=2500):
    """Compress and resize image to reduce memory and API payload."""
    try:
        with Image.open(filepath) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Resize if too large
            if max(img.size) > max_dimension:
                ratio = max_dimension / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                print(f"[DEBUG] Resized image to {new_size}")
            
            # Compress to JPEG with high quality
            buffer = io.BytesIO()
            quality = 90  # Start higher for better OCR
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            
            # Reduce quality if still too large
            while buffer.tell() > max_size_kb * 1024 and quality > 50:
                buffer.seek(0)
                buffer.truncate()
                quality -= 10
                img.save(buffer, format='JPEG', quality=quality, optimize=True)
            
            buffer.seek(0)
            result = base64.b64encode(buffer.read()).decode('utf-8')
            size_kb = len(result) // 1024
            buffer.close()
            print(f"[DEBUG] Compressed image to {size_kb}KB base64 (Quality: {quality})")
            return result, 'image/jpeg'
    except Exception as e:
        print(f"[WARN] Image compression failed: {e}, using original")
        return None, None

def extract_data_from_image(filepath):
    """Extract data from an image using OpenAI Vision API."""
    if not openai_client:
        print("Warning: OPENAI_API_KEY not set. Skipping image extraction.")
        return {}
    
    try:
        # Try compressed version first (saves memory)
        base64_image, mime_type = compress_image_for_api(filepath)
        
        if not base64_image:
            # Fallback to original
            with open(filepath, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            ext = filepath.lower().split('.')[-1]
            mime_type = f"image/{ext}" if ext in ['png', 'jpg', 'jpeg'] else "image/jpeg"
            if ext == 'jpg':
                mime_type = "image/jpeg"
        
        # Improved prompt for Brazilian identity documents with emphasis on OCR correction
        identity_prompt = """Você é um especialista em OCR e extração de dados de documentos brasileiros.

Analise esta imagem de documento de identificação (CNH, RG, CIN, Passaporte) e extraia os dados com MÁXIMA precisão.

CAMPOS CRÍTICOS (Obrigatórios):
- name: Nome completo (NOME). Se estiver em várias linhas, concatene. Corrija erros óbvios de OCR (ex: '0' em vez de 'O', '1' em vez de 'I').
- cpf: O CPF é crucial. Procure formato XXX.XXX.XXX-XX. Se houver dígitos suspeitos, tente inferir pelo contexto.
- birth_date: Data de nascimento (NASCIMENTO). Formato DD/MM/AAAA.

CAMPOS ADICIONAIS:
- nationality: Nacionalidade.
- civil_state: Estado civil.
- rg: Número do RG/Registro Geral.
- rg_issuer: Órgão emissor (ex: SSP/SP, DETRAN/RJ).
- cnh_number: Número de registro da CNH (se for CNH).
- address: Endereço (se houver).
- mother_name: Nome da mãe (FILIAÇÃO).
- father_name: Nome do pai (FILIAÇÃO).

DICAS DE EXTRAÇÃO:
- CNH: O nome fica no topo. O CPF fica abaixo da foto ou no verso.
- RG Antigo: Nome e filiação no verso.
- CIN (RG Novo): QR Code no verso. Dados principais na frente.
- Ignore marcas d'água, carimbos ou reflexos que atrapalhem a leitura.
- Se um campo estiver ilegível, retorne null para ele.
- Retorne APENAS JSON válido."""

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": identity_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}",
                                "detail": "high"  # Use high detail for better OCR
                            }
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=1000
        )
        content = response.choices[0].message.content
        print(f"[DEBUG] Raw OpenAI Vision response: {content}")
        
        result = json.loads(content)
        print(f"[DEBUG] Parsed JSON: {result}")
        
        # Explicit memory cleanup
        del base64_image
        gc.collect()
        
        return result
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON from OpenAI Vision: {e}. Content: {content}")
        return {}
    except FileNotFoundError:
        print(f"[ERROR] Image file not found: {filepath}")
        return {}
    except Exception as e:
        print(f"[ERROR] OpenAI Image Extraction Error: {e}")
        traceback.print_exc()
        return {}

def extract_address_from_proof(filepath):
    """Extract address data from utility bills or address proof documents."""
    if not openai_client:
        print("Warning: OPENAI_API_KEY not set. Skipping address extraction.")
        return {}
    
    try:
        # Use compression for address proofs too
        base64_image, mime_type = compress_image_for_api(filepath)
        
        if not base64_image:
            with open(filepath, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            ext = filepath.lower().split('.')[-1]
            mime_type = f"image/{ext}" if ext in ['png', 'jpg', 'jpeg'] else "image/jpeg"
            if ext == 'jpg':
                mime_type = "image/jpeg"

        
        address_prompt = """Você é um especialista em OCR de comprovantes de residência brasileiros.

Analise esta imagem (conta de luz, água, telefone, internet ou fatura de cartão) e extraia o endereço com precisão.

CAMPOS OBRIGATÓRIOS:
- street: Logradouro (Rua, Av, Praça, etc) + Nome.
- number: Número do imóvel. Se for 'S/N', retorne 'S/N'.
- complement: Complemento (Ex: Apto 101, Bloco B).
- neighborhood: Bairro.
- city: Cidade.
- state: Estado (UF, sigla de 2 letras).
- zipcode: CEP (formato XXXXX-XXX).

DICAS:
- O endereço geralmente fica no topo, perto do nome do titular, ou no corpo da fatura.
- Ignore endereços da empresa emissora da conta (ex: Enel, Sabesp, Claro). Procure o endereço do CLIENTE/DESTINATÁRIO.
- Se houver códigos de barras ou números aleatórios, IGNORE.
- Corrija erros comuns de OCR (ex: 'Rva' -> 'Rua').

Retorne APENAS um objeto JSON válido."""

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": address_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=800
        )
        result = json.loads(response.choices[0].message.content)
        print(f"[DEBUG] Address proof extraction result: {result}")
        return result
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON from address extraction: {e}")
        return {}
    except FileNotFoundError:
        print(f"[ERROR] Address file not found: {filepath}")
        return {}
    except Exception as e:
        print(f"[ERROR] Address Extraction Error: {e}")
        return {}

def extract_data_with_mistral_chat(text):
    """Parse extracted text using Mistral chat API (text only, not vision)."""
    if not mistral_client or not text:
        return None
    
    try:
        print(f"[DEBUG] Using Mistral chat for text parsing, length: {len(text)}")
        
        assert mistral_client is not None  # Already checked above
        
        prompt = """Analise o texto a seguir e extraia as informações em formato JSON.

Para documentos de identidade (RG, CNH, CIN):
- name (Nome Completo)
- nationality (Nacionalidade)  
- civil_state (Estado Civil, se visível)
- birth_date (Data de Nascimento no formato DD/MM/AAAA)
- cpf (CPF, se visível)
- address (Endereço completo formatado como: Rua Nome, Número, Bairro, Cidade/UF, CEP)

Para documentos de empresa (Contrato Social, Cartão CNPJ):
- company_name (Razão Social completa)
- company_address (Endereço da Sede formatado como: Logradouro, Número, Complemento, Bairro, Cidade/UF, CEP 00000-000)
- company_object (Objeto Social resumido)
- company_cnae_list (Lista de CNAEs/Atividades separadas por vírgula)
- start_date (Data de Início no formato DD/MM/AAAA)
- capital_currency (Capital Social em R$)
- total_quotas (Total de Quotas)
- quota_value (Valor por Quota)
- forum_city (Cidade do Foro)

IMPORTANTE: Formate os endereços de forma limpa e legível, removendo quebras de linha e caracteres estranhos.

Retorne APENAS o JSON. Texto do documento:
"""
        response = mistral_client.chat.complete(
            model="mistral-small-latest",  # Text model, not vision
            messages=[
                {"role": "user", "content": f"{prompt}\n\n{text[:10000]}"}
            ]
        )
        
        content = response.choices[0].message.content
        print(f"[DEBUG] Mistral chat response: {content[:300]}...")
        
        # Try to find JSON object with possibly nested braces
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            print(f"[DEBUG] Mistral extracted: {result}")
            return result
        return {}
        
    except Exception as e:
        print(f"[ERROR] Mistral chat error: {e}")
        return None

def convert_pdf_to_image(filepath):
    """Convert PDF first page to image for OCR processing."""
    print(f"[DEBUG] Converting PDF to image: {filepath}")
    
    # Try pdf2image first (requires poppler)
    if PDF2IMAGE_AVAILABLE and convert_from_path is not None:
        try:
            print("[DEBUG] Attempting pdf2image conversion with high DPI...")
            images = convert_from_path(filepath, first_page=1, last_page=1, dpi=300)  # Professional OCR standard
            if images:
                img_path = filepath.replace('.pdf', '_page1.png')
                images[0].save(img_path, 'PNG')
                del images  # Explicit cleanup
                gc.collect()
                print(f"[DEBUG] Content check: {os.path.getsize(img_path)} bytes")
                print(f"[DEBUG] Converted PDF to image: {img_path}")
                return img_path
            else:
                print("[WARN] pdf2image returned empty list")
        except Exception as e:
            print(f"[WARN] PDF to image conversion failed: {e}")
    
    # Fallback to PyMuPDF (fitz)
    if FITZ_AVAILABLE and fitz is not None:
        try:
            print("[DEBUG] Attempting PyMuPDF (fitz) conversion...")
            doc = fitz.open(filepath)
            if doc.page_count < 1:
                print("[ERROR] PDF has no pages")
                return None
                
            page = doc[0]
            pix = page.get_pixmap(dpi=150)  # Optimized for free tier memory limits
            img_path = filepath.replace('.pdf', '_page1.png')
            pix.save(img_path)
            del pix  # Explicit cleanup
            doc.close()
            gc.collect()
            
            if os.path.exists(img_path):
                print(f"[DEBUG] Content check: {os.path.getsize(img_path)} bytes")
                print(f"[DEBUG] Converted PDF to image with PyMuPDF: {img_path}")
                return img_path
            else:
                print("[ERROR] PyMuPDF claimed success but file not found")
                
        except Exception as e2:
            print(f"[WARN] PyMuPDF conversion also failed: {e2}")
            traceback.print_exc()
    else:
        print(f"[WARN] PyMuPDF unavailable (Available={FITZ_AVAILABLE}, Module={fitz})")
    
    print("[WARN] No PDF to image converter available or all failed")
    return None

def extract_document_data(filepath):
    """Main extraction function - handles both text-based and image-based documents."""
    print(f"[DEBUG] Extracting data from: {filepath}")
    
    ext = filepath.lower().split('.')[-1]
    
    if ext == 'pdf':
        # For PDFs: first try text extraction
        text = extract_text_from_pdf(filepath)
        text_length = len(text.strip()) if text else 0
        print(f"[DEBUG] PDF text extracted, length: {text_length}")
        
        # If PDF has substantial text (>500 chars), use text parsing
        if text_length > 500:
            print(f"[DEBUG] Text-based PDF detected, using Mistral/OpenAI text parsing")
            
            # Try Mistral first (it's free for text parsing)
            result = extract_data_with_mistral_chat(text)
            if result is not None and len(result) > 0:
                print(f"[DEBUG] Mistral parsing succeeded with {len(result)} fields")
                return result
            
            # Fallback to OpenAI
            print(f"[DEBUG] Falling back to OpenAI for text parsing")
            return extract_data_with_ai(text)
        else:
            # Image-based PDF (like identity documents) - need OCR
            print(f"[DEBUG] Image-based PDF detected ({text_length} chars), using Vision API")
            
            # Try to convert PDF to image first
            img_path = convert_pdf_to_image(filepath)
            if img_path:
                result = extract_data_from_image(img_path)
                if result:
                    return result
            
            # If conversion failed, try sending PDF directly to OpenAI Vision (if it supports it or fallback)
            print("[WARN] PDF-to-Image conversion failed. Sending PDF path to extraction (might fail if not image).")
            # For now, if image conversion fails for a PDF, we might be out of luck unless we treat it as text
            # But let's check:
            return extract_data_from_image(filepath) # This will likely fail or try to read bytes as image
            
    elif ext in ['jpg', 'jpeg', 'png']:
        # For images: use OpenAI Vision directly
        print(f"[DEBUG] Image file detected, sending to OpenAI Vision: {filepath}")
        return extract_data_from_image(filepath)
    
    print(f"[WARN] Unsupported file extension: {ext}")
    return {}

def is_contract_complete(contract):
    """
    Check if a contract is complete (all fields filled, no placeholders).
    Returns tuple: (is_complete: bool, missing_fields: list)
    """
    # Define required fields based on form inputs
    required_partner_fields = [
        'name', 'nationality', 'civil_state', 'profession', 
        'birth_date', 'cpf', 'address', 'quotas', 'amount', 'percent'
    ]
    # Note: 'regime' is skipped as it depends on civil_state
    
    required_company_fields = [
        'company_name', 'company_address', 'company_object', 
        'company_cnae_list', 'start_date', 'capital_currency', 
        'signature_date'
    ]

    missing_fields = []
    
    # Helper to check if value is empty or placeholder
    def is_empty(val):
        if val is None: return True
        s = str(val).strip()
        # Check for empty, "None", "undefined", or common placeholders like "..." or "_"
        if s == '' or s.lower() in ['none', 'null', 'undefined'] or s.startswith('...') or s.startswith('___'):
            return True
        return False

    # Check partners
    partners = contract.get('partners', [])
    if not partners:
        missing_fields.append('no_partners_added')
    
    for i, partner in enumerate(partners):
        for field in required_partner_fields:
            if is_empty(partner.get(field)):
                missing_fields.append(f'partner_{i}_{field}')

    # Check company data
    company_data = contract.get('company_data', {})
    if not company_data:
        missing_fields.append('no_company_data')
    else:
        for field in required_company_fields:
            if is_empty(company_data.get(field)):
                missing_fields.append(f'company_{field}')
    
    is_complete = len(missing_fields) == 0
    return is_complete, missing_fields

@app.route('/')
def index():
    """Dashboard page - lists all contracts from Supabase."""
    contracts = []
    drafts_count = 0
    completed_count = 0
    
    if supabase_client:
        try:
            print("[DEBUG] Fetching contracts from Supabase...")
            response = supabase_client.table('contracts').select('*').order('created_at').execute()
            contracts = response.data if response.data else []
            print(f"[DEBUG] Fetched {len(contracts)} contracts")
            
            # Show newest first
            contracts.reverse()
            
            for contract in contracts:
                # Ensure partners is a list
                if isinstance(contract.get('partners'), str):
                    try:
                        contract['partners'] = json.loads(contract['partners'])
                    except:
                        contract['partners'] = []
                
                # Ensure company_data is a dict
                if isinstance(contract.get('company_data'), str):
                    try:
                        contract['company_data'] = json.loads(contract['company_data'])
                    except:
                        contract['company_data'] = {}

                is_complete, missing = is_contract_complete(contract)
                contract['is_complete'] = is_complete
                contract['missing_fields'] = missing
                
                # Use company_data fields for the contract if top-level fields are missing
                if not contract.get('name') or contract.get('name') == 'Novo Contrato':
                    c_data = contract.get('company_data', {})
                    if isinstance(c_data, dict):
                        contract['name'] = c_data.get('company_name', contract.get('name', 'Sem Nome'))

                # Set effective status
                if not is_complete:
                    contract['effective_status'] = 'draft'
                else:
                    contract['effective_status'] = 'completed'
            drafts_count = len([c for c in contracts if c.get('effective_status', 'draft') == 'draft'])
            completed_count = len([c for c in contracts if c.get('effective_status') == 'completed'])
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch contracts: {e}")
            traceback.print_exc()
    
    return render_template('dashboard.html', 
                         contracts=contracts,
                         drafts_count=drafts_count,
                         completed_count=completed_count)

@app.route('/config')
def config():
    return render_template('config.html')

@app.route('/upload')
def upload():
    try:
        partners = max(1, min(10, int(request.args.get('partners', 2))))
    except (ValueError, TypeError):
        partners = 2
    return render_template('upload.html', partner_count=partners)

@app.route('/process', methods=['POST'])
def process():
    try:
        partner_count = max(1, min(10, int(request.form.get('partner_count', 2))))
    except (ValueError, TypeError):
        partner_count = 2
    partners_data = []
    company_data = {}

    # Check for API keys
    if not openai_client and not mistral_client:
        flash('AVISO: Chaves de API (OpenAI/Mistral) não configuradas. A extração automática não funcionará.', 'error')

    # 1. Process Partners
    for i in range(partner_count):
        files = request.files.getlist(f'files_partner_{i}[]')
        address_files = request.files.getlist(f'files_address_{i}[]')
        
        # Initialize with default empty values so the form always has fields
        partner_info = {
            'id': i,
            'name': '',
            'nationality': '',
            'civil_state': '',
            'regime': '',
            'profession': '',
            'birth_date': '',
            'cpf': '',
            'address': '',
            'quotas': '',
            'amount': '',
            'percent': ''
        }
        
        print(f"[DEBUG] Partner {i}: Found {len(files)} identity files, {len(address_files)} address files")
        
        # Process identity documents (CNH, CIN, RG)
        for file in files:
            if file.filename:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"p{i}_{file.filename}")
                file.save(filepath)
                print(f"[DEBUG] Saved identity file: {filepath}")
                
                # Use unified extraction (Mistral OCR preferred, OpenAI fallback)
                extracted = extract_document_data(filepath)
                if extracted:
                    print(f"[DEBUG] Extracted identity data for partner {i}: {extracted}")
                    partner_info.update(extracted)
                
                # Clean up uploaded file immediately to save memory
                try:
                    os.remove(filepath)
                    print(f"[DEBUG] Cleaned up: {filepath}")
                except:
                    pass
        
        # Process address proof documents (utility bills, bank statements)
        for addr_file in address_files:
            if addr_file.filename:
                addr_filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"addr_{i}_{addr_file.filename}")
                addr_file.save(addr_filepath)
                print(f"[DEBUG] Saved address proof file: {addr_filepath}")
                
                # First try to extract text from PDF
                ext = addr_filepath.lower().split('.')[-1]
                img_path = None
                if ext == 'pdf':
                    # Convert PDF to image for address extraction
                    img_path = convert_pdf_to_image(addr_filepath)
                    if img_path:
                        addr_data = extract_address_from_proof(img_path)
                    else:
                        addr_data = extract_address_from_proof(addr_filepath)
                else:
                    addr_data = extract_address_from_proof(addr_filepath)
                
                # Clean up temp converted image
                if img_path and os.path.exists(img_path):
                    try:
                        os.remove(img_path)
                        print(f"[DEBUG] Cleaned temp image: {img_path}")
                    except:
                        pass
                
                if addr_data:
                    print(f"[DEBUG] Extracted address data for partner {i}: {addr_data}")
                    # Use full_address if available, otherwise construct from parts
                    if addr_data.get('full_address'):
                        partner_info['address'] = addr_data['full_address']
                    elif addr_data.get('street'):
                        # Construct address from parts
                        parts = [
                            addr_data.get('street', ''),
                            addr_data.get('number', ''),
                            addr_data.get('complement', ''),
                            addr_data.get('neighborhood', ''),
                            f"{addr_data.get('city', '')}/{addr_data.get('state', '')}",
                            f"CEP {addr_data.get('zip_code', '')}"
                        ]
                        partner_info['address'] = ', '.join(p for p in parts if p and p != '/' and p != 'CEP ')
                
                # Clean up address file
                try:
                    os.remove(addr_filepath)
                    print(f"[DEBUG] Cleaned up: {addr_filepath}")
                except:
                    pass
        
        partners_data.append(partner_info)
        print(f"[DEBUG] Partner {i} final data: {partner_info}")
        
        # Memory cleanup after each partner
        gc.collect()
        print(f"[DEBUG] Memory cleaned after partner {i}")

    # 2. Process Company Docs
    company_files = request.files.getlist('files_company[]')
    for file in company_files:
        if file.filename:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"company_{file.filename}")
            file.save(filepath)
            print(f"[DEBUG] Saved company file: {filepath}")
            
            # Use unified extraction (Mistral OCR preferred, OpenAI fallback)
            extracted = extract_document_data(filepath)
            if extracted:
                print(f"[DEBUG] Extracted company data: {extracted}")
                company_data.update(extracted)
            
            # Clean up company file immediately
            try:
                os.remove(filepath)
                print(f"[DEBUG] Cleaned up: {filepath}")
            except:
                pass
    
    # Final memory cleanup
    gc.collect()
    print("[DEBUG] Final memory cleanup completed")

    # Store in session or pass directly to form
    print(f"[DEBUG] Final partners count: {len(partners_data)}")
    print(f"[DEBUG] Final company data: {company_data}")

    # Flash messages based on extraction result
    has_data = any(p.get('name') for p in partners_data) or company_data.get('company_name')
    if not has_data:
        flash('Não foi possível extrair dados automaticamente. Por favor, preencha o formulário manualmente.', 'warning')
    else:
        flash('Dados extraídos com sucesso! Por favor, revise as informações.', 'success')

    # Save DRAFT to Supabase
    contract_id = None
    if supabase_client:
        try:
            draft_payload = {
                'name': company_data.get('company_name') or f'Rascunho {len(partners_data)} Sócios',
                'status': 'draft',
                'partners': partners_data,
                'company_data': company_data,
                'updated_at': 'now()'
            }
            res = supabase_client.table('contracts').insert(draft_payload).execute()
            if res.data:
                contract_id = res.data[0]['id']
                print(f"[DEBUG] Created DRAFT contract {contract_id}")
        except Exception as e:
            print(f"[ERROR] Failed to save draft: {e}")
            flash('Aviso: Não foi possível salvar o rascunho no banco de dados.', 'warning')
    
    return render_template('form.html', 
                         partners=partners_data,
                         company=company_data if company_data else {},
                         contract_id=contract_id,
                         partner_count=len(partners_data))

@app.route('/generate', methods=['POST'])
def generate():
    try:
        print("[DEBUG] Starting generate route")
        
        # Reconstruct data from form
        partners = []
        
        # Simple parser for "partner_i_field"
        p_indices = set()
        for key in request.form.keys():
            if key.startswith('partner_') and '_' in key:
                parts = key.split('_')
                if len(parts) >= 2 and parts[1].isdigit():
                    p_indices.add(int(parts[1]))
        
        print(f"[DEBUG] Found partner indices: {p_indices}")
        
        for i in sorted(list(p_indices)):
            p_data = {
                'name': request.form.get(f'partner_{i}_name', ''),
                'nationality': request.form.get(f'partner_{i}_nationality', ''),
                'civil_state': request.form.get(f'partner_{i}_civil_state', ''),
                'regime': request.form.get(f'partner_{i}_regime', ''),
                'profession': request.form.get(f'partner_{i}_profession', ''),
                'birth_date': request.form.get(f'partner_{i}_birth_date', ''),
                'cpf': request.form.get(f'partner_{i}_cpf', ''),
                'address': request.form.get(f'partner_{i}_address', ''),
                'quotas': request.form.get(f'partner_{i}_quotas', ''),
                'amount': request.form.get(f'partner_{i}_amount', ''),
                'percent': request.form.get(f'partner_{i}_percent', '')
            }
            partners.append(p_data)
            print(f"[DEBUG] Partner {i} data: {p_data}")
            
        company_data = {
            'company_name': request.form.get('company_name', ''),
            'company_address': request.form.get('company_address', ''),
            'company_object': request.form.get('company_object', ''),
            'company_cnae_list': request.form.get('company_cnae_list', ''),
            'start_date': request.form.get('start_date', ''),
            'capital_currency': request.form.get('capital_currency', ''),
            'signature_date': request.form.get('signature_date', ''),
            'partners': partners,
            'administrator_names': ", ".join([p['name'] for p in partners if p['name']])
        }
        
        print(f"[DEBUG] Company data: {company_data}")
        
        # Save to Supabase
        contract_id = request.form.get('contract_id')
        if supabase_client:
            try:
                contract_payload = {
                    'name': company_data.get('company_name') or 'Contrato Sem Nome',
                    'status': 'completed',
                    'partners': partners,
                    'company_data': company_data,
                    'updated_at': 'now()'
                }
                
                if contract_id:
                    # Update existing
                    supabase_client.table('contracts').update(contract_payload).eq('id', contract_id).execute()
                    print(f"[DEBUG] Updated contract {contract_id} in Supabase")
                else:
                    # Create new
                    result = supabase_client.table('contracts').insert(contract_payload).execute()
                    if result.data:
                        contract_id = result.data[0]['id']
                        print(f"[DEBUG] Created new contract {contract_id} in Supabase")
            except Exception as e:
                print(f"[ERROR] Failed to save to Supabase: {e}")

        # Generate Document
        template_path = os.path.join(BASE_DIR, 'contract_template.docx')
        if not os.path.exists(template_path):
            flash('Erro: Template de contrato não encontrado.', 'error')
            return redirect(url_for('index'))
            
        output_filename = f"contract_{contract_id or 'temp'}.docx"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        print(f"[DEBUG] Template path: {template_path}")
        print(f"[DEBUG] Output path: {output_path}")
        
        doc = DocxTemplate(template_path)
        # Apply placeholders to ensure consistent download experience
        doc.render(apply_placeholders(company_data))
        doc.save(output_path)
        
        print("[DEBUG] Document generated successfully")
        display_name = f"Contrato Social - {company_data.get('company_name', 'Novo')}.docx"
        return render_template('download.html', filename=output_filename, display_name=display_name)
    except Exception as e:
        print(f"[ERROR] Generate failed: {e}")
        traceback.print_exc()
        return f"<h1>Erro ao gerar contrato</h1><pre>{e}</pre>", 500

@app.route('/download/<filename>')
def download_file(filename):
    # Sanitize filename to prevent directory traversal
    safe_filename = os.path.basename(filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    
    if not os.path.exists(path):
        return "Arquivo não encontrado", 404
        
    custom_name = request.args.get('name')
    return send_file(path, as_attachment=True, download_name=custom_name if custom_name else safe_filename)

# API Routes for Dashboard
@app.route('/api/contracts/<id>', methods=['DELETE'])
def delete_contract(id):
    if not supabase_client:
        return jsonify({'error': 'Database not configured'}), 503
    
    try:
        supabase_client.table('contracts').delete().eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        print(f"[ERROR] Delete failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/contract/<id>/edit')
def edit_contract(id):
    if not supabase_client:
        return redirect(url_for('index'))
        
    try:
        result = supabase_client.table('contracts').select('*').eq('id', id).execute()
        if not result.data:
            return "Contrato não encontrado", 404
            
        contract = result.data[0]
        partners = contract.get('partners', [])
        company = contract.get('company_data', {})
        
        return render_template('form.html', 
                             partners=partners, 
                             company=company, 
                             contract_id=id,
                             partner_count=len(partners))
    except Exception as e:
        print(f"[ERROR] Edit load failed: {e}")
        return f"Erro ao carregar contrato: {e}", 500

def apply_placeholders(data):
    """
    Recursively replaces empty values in the data dictionary with placeholders.
    """
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                new_data[k] = apply_placeholders(v)
            elif not v or str(v).strip() == "":
                # Generate placeholder based on key
                placeholder = f"[{k.upper().replace('_', ' ')}]"
                
                # Custom mappings for better readability
                mappings = {
                    'name': '[NOME COMPLETO]',
                    'cpf': '[CPF]',
                    'rg': '[RG]',
                    'nationality': '[NACIONALIDADE]',
                    'civil_state': '[ESTADO CIVIL]',
                    'profession': '[PROFISSÃO]',
                    'address': '[ENDEREÇO COMPLETO]',
                    'company_name': '[RAZÃO SOCIAL]',
                    'company_address': '[ENDEREÇO DA SEDE]',
                    'capital_currency': '[CAPITAL R$]',
                    'capital_amount_text': '[CAPITAL POR EXTENSO]',
                    'start_date': '[DATA DE INÍCIO]',
                    'signature_date': '[DATA DE ASSINATURA]'
                }
                
                # Check for partner specific keys
                if k in mappings:
                    placeholder = mappings[k]
                elif 'partner' in k and 'name' in k:
                    placeholder = '[NOME DO SÓCIO]'
                
                new_data[k] = placeholder
            else:
                new_data[k] = v
        return new_data
    elif isinstance(data, list):
        return [apply_placeholders(item) for item in data]
    return data

@app.route('/contract/<id>/download')
def download_contract(id):
    if not supabase_client:
        return redirect(url_for('index'))
        
    try:
        result = supabase_client.table('contracts').select('*').eq('id', id).execute()
        if not result.data:
            return "Contrato não encontrado", 404
            
        contract = result.data[0]
        company_data = contract.get('company_data', {}) or {}
        status = contract.get('status', 'draft')
        
        # Check if force download is requested
        force_download = request.args.get('force') == 'true'
        
        # If force download and data is empty/incomplete, populate with defaults to ensure keys exist
        if force_download:
             # Standard keys expected by the template
            default_keys = [
                'company_name', 'company_address', 'company_object', 'company_cnae_list',
                'start_date', 'capital_currency', 'capital_amount_text', 'total_quotas',
                'quota_value', 'forum_city', 'signature_date', 'administrator_names'
            ]
            for key in default_keys:
                if key not in company_data or not company_data[key]:
                    company_data[key] = ""
            
            # Ensure at least one dummy partner if none exist, so the loop in docx works
            if 'partners' not in company_data or not company_data['partners']:
                company_data['partners'] = [{
                    'name': '', 'nationality': '', 'civil_state': '', 'regime': '',
                    'profession': '', 'birth_date': '', 'cpf': '', 'address': '',
                    'quotas': '', 'amount': '', 'percent': ''
                }]

        if not company_data and not force_download:
            return "Dados do contrato incompletos (use 'Baixar Assim Mesmo' para forçar)", 400
            
        # Re-generate document
        template_path = os.path.join(BASE_DIR, 'contract_template.docx')
        if not os.path.exists(template_path):
            return "Template de contrato não encontrado", 500
            
        output_filename = f"contract_{id}.docx"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        # Apply placeholders if it's a draft or force download
        data_to_render = company_data
        if status != 'completed' or force_download:
             data_to_render = apply_placeholders(company_data)
        
        doc = DocxTemplate(template_path)
        doc.render(data_to_render)
        doc.save(output_path)
        
        return send_file(output_path, as_attachment=True, download_name=f"Contrato Social - {company_data.get('company_name', 'Novo')}.docx")
    except Exception as e:
        print(f"[ERROR] Download generate failed: {e}")
        traceback.print_exc()
        return f"Erro ao gerar download: {e}", 500

@app.route('/api/extract-document', methods=['POST'])
def extract_single_document():
    """
    API endpoint to extract data from a single document.
    Designed to be called sequentially from frontend to avoid memory overload.
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        
        file = request.files['file']
        doc_type = request.form.get('type', 'identity')  # identity, address, company
        
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        print(f"[DEBUG] Processing single file: {file.filename} (type: {doc_type})")
        
        # Save file temporarily
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_{int(time.time())}_{file.filename}")
        file.save(filepath)
        
        extracted_data = {}
        
        try:
            # 1. Extract data based on type
            if doc_type == 'address':
                # For address documents
                # First try to convert PDF to image if needed
                ext = filepath.lower().split('.')[-1]
                img_path = None
                if ext == 'pdf':
                    img_path = convert_pdf_to_image(filepath)
                    working_path = img_path if img_path else filepath
                else:
                    working_path = filepath
                
                addr_data = extract_address_from_proof(working_path)
                
                # Cleanup temp image from conversion
                if img_path and os.path.exists(img_path):
                    try:
                        os.remove(img_path)
                    except: pass
                    
                if addr_data:
                    # Format address
                    if addr_data.get('full_address'):
                        extracted_data['address'] = addr_data['full_address']
                    elif addr_data.get('street'):
                        extract_c = addr_data
                        parts = [
                            extract_c.get('street', ''),
                            extract_c.get('number', ''),
                            extract_c.get('complement', ''),
                            extract_c.get('neighborhood', ''),
                            f"{extract_c.get('city', '')}/{extract_c.get('state', '')}" if extract_c.get('city') else '',
                            f"CEP {extract_c.get('zip_code', '')}" if extract_c.get('zip_code') else ''
                        ]
                        extracted_data['address'] = ', '.join(p for p in parts if p and p != '/' and p != 'CEP ')
            
            else:
                # Identity or Company documents (generic extraction)
                extracted_data = extract_document_data(filepath)
        
        except Exception as e:
            print(f"[ERROR] Extraction failure: {e}")
            traceback.print_exc()
        finally:
            # Always clean up the uploaded file
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except:
                    pass
            
            # Explicit GC
            gc.collect()
        
        return jsonify(extracted_data)

    except Exception as e:
        print(f"[ERROR] API Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/process-json', methods=['POST'])
def process_json():
    """Receiver for the consolidated JSON data from client-side sequential processing."""
    try:
        print("[INFO] Received consolidated JSON data")
        data = request.json
        if not data:
             print("[ERROR] No JSON data received in /process-json")
             return jsonify({'error': 'No data received'}), 400
             
        print(f"[DEBUG] JSON payload received, partners: {len(data.get('partners', []))}")
        
        partners_data = data.get('partners', [])
        company_data = data.get('company', {})
        
        # Save to Supabase (Draft)
        contract_id = None
        if supabase_client:
            try:
                draft_payload = {
                    'name': company_data.get('company_name') or f'Rascunho {len(partners_data)} Sócios',
                    'status': 'draft',
                    'partners': partners_data,
                    'company_data': company_data,
                    'updated_at': 'now()'
                }
                res = supabase_client.table('contracts').insert(draft_payload).execute()
                if res.data:
                    contract_id = res.data[0]['id']
                    print(f"[INFO] Created DRAFT contract {contract_id}")
            except Exception as e:
                print(f"[ERROR] Failed to save draft: {e}")
                traceback.print_exc()
        
        has_data = any(p.get('name') for p in partners_data) or company_data.get('company_name')
        if not has_data:
            flash('Aviso: Poucos dados foram extraídos. Preencha manualmente.', 'warning')
        else:
            flash('Processamento concluído com sucesso!', 'success')

        return render_template('form.html', 
                             partners=partners_data,
                             company=company_data,
                             contract_id=contract_id,
                             partner_count=len(partners_data))
                             
    except Exception as e:
        print(f"[ERROR] Process JSON failed: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Diagnostic endpoint to check system status."""
    status = {
        'openai': openai_client is not None,
        'mistral': mistral_client is not None,
        'supabase': supabase_client is not None,
        'upload_folder_exists': os.path.exists(app.config['UPLOAD_FOLDER']),
        'upload_folder_writable': os.access(app.config['UPLOAD_FOLDER'], os.W_OK),
        'environment': 'Vercel' if os.environ.get('VERCEL') else 'Local/Other'
    }
    return jsonify(status)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
