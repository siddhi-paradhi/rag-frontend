import os
from langchain_community.document_loaders import PyMuPDFLoader, TextLoader, UnstructuredWordDocumentLoader

def load_docs(source_dir="data"):
    docs = []
    for file in os.listdir(source_dir):
        path = os.path.join(source_dir, file)

        try:
            if file.endswith(".pdf"):
                loader = PyMuPDFLoader(path)
            elif file.endswith(".docx"):
                loader = UnstructuredWordDocumentLoader(path)
            elif file.endswith(".txt"):
                loader = TextLoader(path, encoding="utf-8")
            else:
                print(f"Skipped unsupported file type: {file}")
                continue

            docs.extend(loader.load())

        except Exception as e:
            print(f"Error loading {file}: {e}")
    
    return docs
