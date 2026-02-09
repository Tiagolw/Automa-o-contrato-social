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

# Optional imports for PDF to image conversion
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    convert_from_path = None  # type: ignore
    PDF2IMAGE_AVAILABLE = False

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

def compress_image_for_api(filepath, max_size_kb=500, max_dimension=1500):
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
            
            # Compress to JPEG
            buffer = io.BytesIO()
            quality = 85
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            
            # Reduce quality if still too large
            while buffer.tell() > max_size_kb * 1024 and quality > 30:
                buffer.seek(0)
                buffer.truncate()
                quality -= 10
                img.save(buffer, format='JPEG', quality=quality, optimize=True)
            
            buffer.seek(0)
            result = base64.b64encode(buffer.read()).decode('utf-8')
            buffer.close()
            print(f"[DEBUG] Compressed image to {len(result) // 1024}KB base64")
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
        
        # Improved prompt for Brazilian identity documents
        identity_prompt = """Você é um especialista em extração de dados de documentos brasileiros.
        
Analise esta imagem de documento de identificação (pode ser CNH, CIN, RG, ou outro documento de identidade brasileiro) e extraia TODAS as informações visíveis.

CAMPOS OBRIGATÓRIOS (extraia mesmo se parcialmente visíveis):
- name: Nome completo EXATAMENTE como aparece no documento
- birth_date: Data de nascimento no formato DD/MM/AAAA
- cpf: CPF com 11 dígitos (pode ter pontos e traço)

CAMPOS OPCIONAIS (extraia se visíveis):
- nationality: Nacionalidade (geralmente "BRASILEIRA" ou "BRASILEIRO")
- civil_state: Estado civil se visível
- rg: Número do RG/Identidade
- rg_issuer: Órgão emissor do RG (ex: SSP/SC)
- cnh_number: Número de registro da CNH se for CNH
- cnh_validity: Data de validade da CNH
- cnh_category: Categoria da CNH (A, B, AB, etc)
- address: Endereço completo se visível
- mother_name: Nome da mãe
- father_name: Nome do pai

INSTRUÇÕES IMPORTANTES:
1. Leia o documento com MUITA atenção, letra por letra
2. Para CNH digital ou física, o nome está no campo "NOME"
3. Para CIN, o nome está próximo à foto
4. Datas devem estar no formato DD/MM/AAAA
5. Se não conseguir ler um campo, omita-o do JSON
6. NÃO invente dados - só inclua o que está claramente visível

Retorne APENAS um objeto JSON válido, sem explicações."""

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
            max_tokens=1000  # Increased for more complete extraction
        )
        result = json.loads(response.choices[0].message.content)
        print(f"[DEBUG] OpenAI Image extraction result: {result}")
        
        # Explicit memory cleanup
        del base64_image
        gc.collect()
        
        return result
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON from OpenAI Vision: {e}")
        return {}
    except FileNotFoundError:
        print(f"[ERROR] Image file not found: {filepath}")
        return {}
    except Exception as e:
        print(f"[ERROR] OpenAI Image Extraction Error: {e}")
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

        
        address_prompt = """Você é um especialista em extração de dados de comprovantes de endereço brasileiros.

Analise esta imagem de comprovante de endereço (pode ser conta de luz, água, telefone, internet, banco, ou outro) e extraia as informações.

CAMPOS A EXTRAIR:
- holder_name: Nome do titular/cliente que aparece no documento
- street: Nome da rua/avenida/logradouro
- number: Número do imóvel
- complement: Complemento (apartamento, bloco, sala, etc) - se houver
- neighborhood: Bairro
- city: Cidade
- state: Estado (sigla UF, ex: SP, SC, RJ)
- zip_code: CEP no formato 00000-000
- full_address: Endereço completo formatado como: "Rua Nome, 123, Complemento, Bairro, Cidade/UF, CEP 00000-000"

INSTRUÇÕES:
1. Leia cuidadosamente todos os campos de endereço
2. O CEP geralmente está próximo ao endereço
3. Formate o endereço de forma limpa e legível
4. Se não conseguir ler um campo, omita-o
5. NÃO invente dados

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
    # Try pdf2image first (requires poppler)
    if PDF2IMAGE_AVAILABLE and convert_from_path is not None:
        try:
            images = convert_from_path(filepath, first_page=1, last_page=1, dpi=100)  # Reduced from 150 for memory
            if images:
                img_path = filepath.replace('.pdf', '_page1.png')
                images[0].save(img_path, 'PNG')
                del images  # Explicit cleanup
                gc.collect()
                print(f"[DEBUG] Converted PDF to image: {img_path}")
                return img_path
        except Exception as e:
            print(f"[WARN] PDF to image conversion failed: {e}")
    
    # Fallback to PyMuPDF (fitz)
    if FITZ_AVAILABLE and fitz is not None:
        try:
            doc = fitz.open(filepath)
            page = doc[0]
            pix = page.get_pixmap(dpi=100)  # Reduced from 150 for memory
            img_path = filepath.replace('.pdf', '_page1.png')
            pix.save(img_path)
            del pix  # Explicit cleanup
            doc.close()
            gc.collect()
            print(f"[DEBUG] Converted PDF to image with PyMuPDF: {img_path}")
            return img_path
        except Exception as e2:
            print(f"[WARN] PyMuPDF conversion also failed: {e2}")
    
    print("[WARN] No PDF to image converter available (pdf2image or PyMuPDF)")
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
            
            # If conversion failed, try sending PDF directly to OpenAI Vision
            return extract_data_from_image(filepath)
            
    elif ext in ['jpg', 'jpeg', 'png']:
        # For images: use OpenAI Vision directly
        print(f"[DEBUG] Image file, using OpenAI Vision: {filepath}")
        return extract_data_from_image(filepath)
    
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
            # Fetch all contracts ordered by creation date (newest first)
            response = supabase_client.table('contracts').select('*').order('created_at').execute()
            contracts = response.data if response.data else []
            # Reverse to show newest first (descending order)
            contracts.reverse()
            
            # Recalculate status based on completeness
            for contract in contracts:
                is_complete, missing = is_contract_complete(contract)
                contract['is_complete'] = is_complete
                contract['missing_fields'] = missing
                
                # Debug logging
                print(f"[DEBUG] Contract '{contract.get('name', 'N/A')}': complete={is_complete}, missing={missing}")
                
                # Set effective status: draft if incomplete, otherwise use saved status
                if not is_complete:
                    contract['effective_status'] = 'draft'
                else:
                    contract['effective_status'] = 'completed'
            
            drafts_count = len([c for c in contracts if c.get('effective_status') == 'draft'])
            completed_count = len([c for c in contracts if c.get('effective_status') == 'completed'])
            print(f"[DEBUG] Dashboard loaded: {len(contracts)} contracts, {drafts_count} drafts, {completed_count} completed")
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
        doc.render(company_data)
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

@app.route('/contract/<id>/download')
def download_contract(id):
    if not supabase_client:
        return redirect(url_for('index'))
        
    try:
        result = supabase_client.table('contracts').select('*').eq('id', id).execute()
        if not result.data:
            return "Contrato não encontrado", 404
            
        contract = result.data[0]
        company_data = contract.get('company_data', {})
        
        if not company_data:
            return "Dados do contrato incompletos", 400
            
        # Re-generate document
        template_path = os.path.join(BASE_DIR, 'contract_template.docx')
        if not os.path.exists(template_path):
            return "Template de contrato não encontrado", 500
            
        output_filename = f"contract_{id}.docx"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        doc = DocxTemplate(template_path)
        doc.render(company_data)
        doc.save(output_path)
        
        return send_file(output_path, as_attachment=True, download_name=f"Contrato Social - {company_data.get('company_name', 'Novo')}.docx")
    except Exception as e:
        print(f"[ERROR] Download generate failed: {e}")
        return f"Erro ao gerar download: {e}", 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
