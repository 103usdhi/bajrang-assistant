import json
import requests
import pypdf


def save_document_metadata(doc_data, supabase_url, headers, log_error):
    try:
        url = f"{supabase_url}/rest/v1/uploaded_documents"
        result = requests.post(url, headers=headers, json=doc_data, timeout=10)
        if result.status_code in [200, 201, 204]:
            return True
        log_error("save_document_metadata", RuntimeError(f"Supabase returned {result.status_code}: {result.text}"))
        return False
    except Exception as e:
        log_error("save_document_metadata", e)
        return False


def get_uploaded_documents(limit, supabase_url, headers, log_error):
    try:
        url = (
            f"{supabase_url}/rest/v1/uploaded_documents"
            f"?select=filename,document_type,created_at,semantic_chunk_count"
            f"&order=created_at.desc"
            f"&limit={limit}"
        )
        result = requests.get(url, headers=headers, timeout=10)
        return result.json() if result.status_code == 200 else []
    except Exception as e:
        log_error("get_uploaded_documents", e)
        return []


def get_documents_summary(get_uploaded_documents, log_error):
    try:
        docs = get_uploaded_documents(limit=10)
        if not docs:
            return "No documents found."
        return json.dumps(docs, indent=2)
    except Exception as e:
        log_error("get_documents_summary", e)
        return "Failed to fetch document summary."


def is_explicit_document_context_request(text, has_explicit_data_action):
    doc_words = ("document", "documents", "pdf", "pdfs", "file", "files", "uploaded")
    return has_explicit_data_action(text) and any(word in text for word in doc_words)


def extract_pdf_text_from_path(pdf_path):
    text_content = ""
    page_count = 0
    with open(pdf_path, "rb") as f:
        reader = pypdf.PdfReader(f)
        page_count = len(reader.pages)
        for page in reader.pages:
            text_content += page.extract_text() or ""
    return text_content, page_count


def split_document_chunks(text_content, chunk_size=8000):
    return [text_content[i:i + chunk_size] for i in range(0, len(text_content), chunk_size)]


def build_document_metadata_payload(filename, file_id, page_count, chunks, text_content, truncate_text):
    return {
        "filename": filename,
        "telegram_file_id": file_id,
        "document_type": "pdf",
        "source": "telegram",
        "page_count": page_count,
        "semantic_chunk_count": len(chunks),
        "storage_status": "processed",
        "extracted_text_summary": truncate_text(text_content, 1000)
    }


def build_document_processing_prompt(chunks, truncate_text):
    summary_text = "\n".join(chunks[:2])
    return (
        "The uploaded document has been preserved as a document record and split into searchable semantic chunks for later retrieval. "
        "Based *only* on the following opening segments, provide a concise overview of what this document is about. "
        "If it is German A1 learning material, identify the main topics.\n\n"
        f"Segments:\n{truncate_text(summary_text, 16000, preserve_newlines=True)}"
    )

