from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import Embeddings
from dotenv import load_dotenv
import os
from PyPDF2 import PdfReader
from ftfy import fix_text
import numpy as np
import json
import chromadb
from chromadb.config import Settings
import uuid
# Defined for tokenization purposes only. All model inference is done using WatsonX API.
from transformers import AutoTokenizer

load_dotenv()

# Replace with your actual IBM Cloud API key and service URL
api_key = os.getenv("WATSONX_APIKEY")
service_url = os.getenv("WATSONX_URL")
project_id  = os.getenv("WATSONX_PROJECT_ID")

creds = Credentials(url=service_url,api_key=api_key)

model_id = "intfloat/multilingual-e5-large"
embed_client = Embeddings(model_id=model_id, credentials=creds, project_id=project_id)

client = chromadb.Client(Settings())

tokenizer = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")

def chunk_text_by_tokens(text, tokenizer, max_tokens=500, prefix="passage: ", overlapping=128):
    prefix_tokens = tokenizer.encode(prefix, add_special_tokens=False)
    max_tokens -= len(prefix_tokens)
    tokens = tokenizer.encode(text, add_special_tokens=False)
    chunks = []
    start = 0
    total_tokens = len(tokens)
    while start < total_tokens:
        end = min(start + max_tokens, total_tokens)
        chunk = tokens[start:end]
        chunks.append(tokenizer.decode(chunk, add_special_tokens=False))
        if end == total_tokens:
            break
        start += max_tokens - overlapping 
        
    return chunks

def embed_text_chunks(text, prefix="passage: "):
    """
    Splits the input text into chunks and returns a dictionary with the segment text and their embeddings.
    The text is split into chunks of a maximum of 512 tokens.
    The dictionary is on the form {"chunk_text": text, "chunk_embedding": [0.1, 0.2, ...]}.
    Returns a list of type: -> list[{"chunk_text": str, "chunk_embedding": list[float]}].
    """
    chunks = chunk_text_by_tokens(text, tokenizer, max_tokens=500, prefix=prefix)
    chunks = [prefix + chunk for chunk in chunks]
    response = embed_client.embed_documents(texts=chunks)

    # Create a list of dictionaries, preserving the order
    results = []
    for chunk, embedding in zip(chunks, response):
        results.append({
            "chunk_text": chunk,
            "chunk_embedding": embedding
        })
    return results

# Load PDF and extract text. Forces UTF-8 encoding.
def preprocess_pdf():
    reader = PdfReader("Unleashing the Power of AI  with IBM watsonxai.pdf")
    text = ""
    for page in reader.pages:
        raw_text = page.extract_text()
        if raw_text:
            utf8_text = raw_text.encode("utf-8", errors="ignore").decode("utf-8")
            text += fix_text(utf8_text)

    chunks = embed_text_chunks(text)
    collection = client.get_or_create_collection(name="segment_vectors")
    for chunk in chunks:
        collection.add(
            documents=[chunk["chunk_text"]],
            embeddings=[chunk["chunk_embedding"]],
            ids=[str(uuid.uuid4())]
        )

# Processes the json file containing fewshot questions and answers, and stores them in the ChromaDB collection.
def preprocess_fewshot():
    with open("fewshot_question_answer.json", "r", encoding="utf-8") as f:
        qas = json.load(f)
    collection = client.get_or_create_collection(name="fewshot_qa_vectors")
    for qa in qas:
        question = qa["question"]
        answer = qa["correct_answer"]
        embedding = embed_query(question)
        doc_id = str(uuid.uuid4())
        collection.add(
            documents=[question],
            embeddings=[embedding],
            ids=[doc_id],
            metadatas=[{"answer": answer}]
        )

def get_similar_fewshot_answers(query, n_results=3):
    """
    Given a user query, retrieves the N closest questions and their answers from the fewshot collection.
    Returns a list of dicts: [{"question": ..., "answer": ...}, ...]
    """
    query_embedding = embed_query(query)
    collection = client.get_collection(name="fewshot_qa_vectors")
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas"]
    )
    # Each result is a list of lists (since batch queries are supported)
    questions = results["documents"][0]
    answers = [meta["answer"] for meta in results["metadatas"][0]]
    fewshot_str = ""
    for q, a in zip(questions, answers):
        fewshot_str += f"Question: {q}\nAnswer: {a}\n\n"
    return fewshot_str

def embed_query(query):
    """
    Takes a query and returns its embedding. 
    Handles the case where the query is too long by splitting it into chunks and calculating the centroid. 
    """
    response = embed_text_chunks(query, prefix="query: ")
    response = [embed['chunk_embedding'] for embed in response]
    response = np.mean(response, axis=0).tolist()
    return response

def get_similar_segments(query, n_results=3):
    query_embedding = embed_query(query)
    collection = client.get_collection(name="segment_vectors")
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "embeddings"]
    )
    return results["documents"][0]
