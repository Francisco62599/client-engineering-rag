from fastapi import FastAPI, Request
from pydantic import BaseModel
import redis
import json
import uuid
from ibm_watsonx_ai import APIClient, Credentials
from ibm_watsonx_ai.foundation_models import ModelInference
from dotenv import load_dotenv
import os
import embedding_handler

load_dotenv()

# Replace with your actual IBM Cloud API key and service URL
api_key = os.getenv("WATSONX_APIKEY")  # Load from .env or set directly
service_url = os.getenv("WATSONX_URL")  # Load from .env or set directly
project_id  = os.getenv("WATSONX_PROJECT_ID")

creds = Credentials(url=service_url, api_key=api_key)
model_id = "meta-llama/llama-3-3-70b-instruct"
parameters = {
    "frequency_penalty": 0,
    "max_tokens": 2000,
    "presence_penalty": 0,
    "temperature": 0,
    "top_p": 1
}
model = ModelInference(
	model_id = model_id,
	params = parameters,
	credentials = creds,
	project_id = project_id,
	)

app = FastAPI()

embedding_handler.preprocess_pdf()
embedding_handler.preprocess_fewshot()

#r = redis.StrictRedis(host='localhost', port=6379, db=0) Only without docker network.
r = redis.StrictRedis(host='redis', port=6379, db=0)

# Message request model
class MessageRequest(BaseModel):
    session_id: str
    message: str


def load_system_prompt(question):
    fewshot_qa = embedding_handler.get_similar_fewshot_answers(question)
    system_prompt = f"""
    You are an AI assistant tasked with answering questions strictly based on the provided context. Follow these guidelines:

    1. Contextual Adherence: Use only the information present in the provided context. Do not incorporate external knowledge or make assumptions beyond the given data.

    2. Evidence-Based Responses: For each answer, cite the specific part of the context that supports your response. If multiple pieces of evidence are relevant, reference each accordingly.

    3. Self-Verification: After formulating your answer, review it to confirm that all statements are directly supported by the context. If any part lacks support, revise or omit it.

    4. Handling Insufficient Information: If the context does not provide enough information to answer the question, respond with: "The provided context does not contain sufficient information to answer this question."

    Maintain clarity and conciseness in your responses, ensuring they are informative and directly tied to the context.
    The expected input format will be:
    Question: <question>
    Context: Segment 1: <context 1>.
    Segment 2: <context 2>.
    Segment 3: <context 3>

    After taking the context into account, the format will be:
    {fewshot_qa}

    Remember to always cite the context in your answers if the section is provided, and to never refer to a specific segment.
    """
    return system_prompt


@app.post("/chat")
def chat(msg: MessageRequest):
    session_data = r.get(msg.session_id)
    session = json.loads(session_data) if session_data else {"backend_history": [], "frontend_history": []}
    
    # Switch system prompt shots by question.
    system_prompt = load_system_prompt(msg.message)
    if session["backend_history"] == []:
        session["backend_history"].append({"role": "system", "content": system_prompt})
    else:
        session["backend_history"][0] = {"role": "system", "content": system_prompt}

    user_message = msg.message
    context = embedding_handler.get_similar_segments(user_message)
    context = str.join(". \n", [f"Segment {i+1}: {segment}" for i, segment in enumerate(context)])
    user_message = f""" Answer the following question, Question: {user_message}
                        Basing your answer in the context, Context: {context}"""

    system_response = model.chat(messages=session["backend_history"] + [{"role": "user", "content": user_message}])
    system_response = system_response["choices"][0]["message"]["content"]

    session["backend_history"].append({"role": "user", "content": user_message})
    session["backend_history"].append({"role": "system", "content": system_response})

    session["frontend_history"].append({"role": "user", "content": msg.message})
    session["frontend_history"].append({"role": "system", "content": system_response})

    # Save updated session
    r.setex(msg.session_id, 3600, json.dumps(session))  # expires in 1 hour

    return {"response": system_response, "history": session["frontend_history"]}



@app.get("/new_session")
def new_session():
    session_id = str(uuid.uuid4())
    session_data = {
        "backend_history": [],
        "frontend_history": []
    }
    r.setex(session_id, 3600, json.dumps(session_data))  # expires in 1 hour
    return {"session_id": session_id}