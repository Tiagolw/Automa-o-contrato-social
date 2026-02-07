import pypdf
import os

pdf_path = r"Reference/0 Contrato Social Constituição ECM COWORKING LTDA.pdf"
output_path = ".tmp/contract_text.txt"

def extract_text_from_pdf(pdf_path):
    try:
        reader = pypdf.PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    if os.path.exists(pdf_path):
        text = extract_text_from_pdf(pdf_path)
        os.makedirs(".tmp", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Text extracted to {output_path}")
    else:
        print(f"File not found: {pdf_path}")
