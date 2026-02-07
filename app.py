from flask import Flask, render_template, request, send_file, redirect, url_for, session
import os
import pypdf
from docx import Document
from docxtpl import DocxTemplate
from openai import OpenAI
from dotenv import load_dotenv
import json
import base64

load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '.tmp'
app.config['SECRET_KEY'] = 'dev_key_very_secret' # Required for session

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
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a legal assistant."},
                {"role": "user", "content": f"{prompt}\n\nText:\n{text[:15000]}"}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"AI Extraction Error: {e}")
        return {}

def extract_data_from_image(filepath):
    """Extract data from an image using OpenAI Vision API."""
    if not openai_client:
        print("Warning: OPENAI_API_KEY not set. Skipping image extraction.")
        return {}
    
    import base64
    
    try:
        with open(filepath, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Determine mime type
        ext = filepath.lower().split('.')[-1]
        mime_type = f"image/{ext}" if ext in ['png', 'jpg', 'jpeg'] else "image/jpeg"
        if ext == 'jpg':
            mime_type = "image/jpeg"
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Extract the following information from this identity document image:
- name (Full Name)
- nationality
- birth_date
- cpf (if visible)
- address (if visible)

Return as minimal valid JSON."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=500
        )
        result = json.loads(response.choices[0].message.content)
        print(f"[DEBUG] OpenAI Image extraction result: {result}")
        return result
    except Exception as e:
        print(f"OpenAI Image Extraction Error: {e}")
        return {}

def extract_data_with_mistral_chat(text):
    """Parse extracted text using Mistral chat API (text only, not vision)."""
    if not mistral_client or not text:
        return None
    
    try:
        print(f"[DEBUG] Using Mistral chat for text parsing, length: {len(text)}")
        
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
        
        # Extract JSON from response
        import re
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
    try:
        from pdf2image import convert_from_path
        import tempfile
        
        # Convert first page only
        images = convert_from_path(filepath, first_page=1, last_page=1, dpi=150)
        if images:
            # Save to temp file
            img_path = filepath.replace('.pdf', '_page1.png')
            images[0].save(img_path, 'PNG')
            print(f"[DEBUG] Converted PDF to image: {img_path}")
            return img_path
    except Exception as e:
        print(f"[WARN] PDF to image conversion failed: {e}")
        # pdf2image requires poppler, try alternative approach
        # Fall back to using fitz (PyMuPDF) if available
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(filepath)
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            img_path = filepath.replace('.pdf', '_page1.png')
            pix.save(img_path)
            doc.close()
            print(f"[DEBUG] Converted PDF to image with PyMuPDF: {img_path}")
            return img_path
        except Exception as e2:
            print(f"[WARN] PyMuPDF conversion also failed: {e2}")
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

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/config')
def config():
    return render_template('config.html')

@app.route('/upload')
def upload():
    partners = int(request.args.get('partners', 2))
    return render_template('upload.html', partner_count=partners)

@app.route('/process', methods=['POST'])
def process():
    partner_count = int(request.form.get('partner_count', 2))
    partners_data = []
    company_data = {}

    print(f"[DEBUG] Processing {partner_count} partners")

    # 1. Process Partners
    for i in range(partner_count):
        files = request.files.getlist(f'files_partner_{i}[]')
        
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
        
        print(f"[DEBUG] Partner {i}: Found {len(files)} files")
        
        for file in files:
            if file.filename:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"p{i}_{file.filename}")
                file.save(filepath)
                print(f"[DEBUG] Saved file: {filepath}")
                
                # Use unified extraction (Mistral OCR preferred, OpenAI fallback)
                extracted = extract_document_data(filepath)
                if extracted:
                    print(f"[DEBUG] Extracted data for partner {i}: {extracted}")
                    partner_info.update(extracted)
        
        partners_data.append(partner_info)
        print(f"[DEBUG] Partner {i} final data: {partner_info}")

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

    # Store in session or pass directly to form
    context = {
        'partners': partners_data,
        'company': company_data if company_data else {}
    }
    
    print(f"[DEBUG] Final context: {context}")
    return render_template('form.html', context=context)

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
            'capital_amount_text': request.form.get('capital_amount_text', ''),
            'total_quotas': request.form.get('total_quotas', ''),
            'quota_value': request.form.get('quota_value', ''),
            'forum_city': request.form.get('forum_city', ''),
            'signature_date': request.form.get('signature_date', ''),
            'partners': partners,
            'administrator_names': ", ".join([p['name'] for p in partners if p['name']])
        }
        
        print(f"[DEBUG] Company data: {company_data}")
        
        template_path = 'contract_template.docx'
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'generated_contract.docx')
        
        print(f"[DEBUG] Template path: {template_path}")
        print(f"[DEBUG] Output path: {output_path}")
        
        doc = DocxTemplate(template_path)
        doc.render(company_data)
        doc.save(output_path)
        
        print("[DEBUG] Document generated successfully")
        return render_template('download.html', filename='generated_contract.docx')
    except Exception as e:
        print(f"[ERROR] Generate failed: {e}")
        import traceback
        traceback.print_exc()
        return f"<h1>Erro ao gerar contrato</h1><pre>{e}</pre>", 500

@app.route('/download/<filename>')
def download_file(filename):
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    return send_file(path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
