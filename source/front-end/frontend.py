import streamlit as st
import requests
import time

#API_URL = "http://localhost:8000"Only without docker network. 
API_URL = "http://backend:8000" 

# Session initialization
if "session_id" not in st.session_state:
    for _ in range(10):
        try:
            response = requests.get(f"{API_URL}/new_session")
            break
        except requests.exceptions.ConnectionError:
            time.sleep(2)
    
    st.session_state["session_id"] = response.json()["session_id"]

st.title("🗨️ Chatbot with Sessions")

# Initialize chat history if not already in session state
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

# Create containers for chat and input
chat_container = st.container()
input_container = st.container()

# Display chat history at the top
with chat_container:
    for entry in st.session_state["chat_history"]:
        if entry.get("role") == "user":
            st.markdown(f"**You:** {entry['content']}")
        elif entry.get("role") == "system":
            st.markdown(f"**Assistant:** {entry['content']}")

# Place input at the bottom
with input_container:
    with st.form(key="chat_form", clear_on_submit=True):
        user_input = st.text_input("You:", key="input")
        submit_button = st.form_submit_button(label="Send")

        if submit_button and user_input:
            message_utf8 = str(user_input).encode("utf-8").decode("utf-8")
            payload = {
                "session_id": st.session_state["session_id"],
                "message": message_utf8
            }
            try:
                response = requests.post(f"{API_URL}/chat", json=payload)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        st.session_state["chat_history"] = data.get("history", [])
                        st.rerun()
                    except requests.exceptions.JSONDecodeError:
                        st.error("Error: Received invalid JSON from the server.")
                else:
                    st.error(f"Error: Server returned status code {response.status_code}")
            except requests.exceptions.RequestException as e:
                st.error(f"Error: Unable to connect to the server. Details: {e}")
