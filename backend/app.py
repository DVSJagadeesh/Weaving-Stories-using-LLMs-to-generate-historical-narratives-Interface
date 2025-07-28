import os
import sys
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

try:
    from firebase_admin import credentials, initialize_app, firestore, auth as firebase_auth
    _firebase_admin_initialized = False
    if '__firebase_config' in globals() and __firebase_config:
        try:
            firebase_config = json.loads(__firebase_config)
            cred = credentials.Certificate(firebase_config)
            initialize_app(cred)
            _firebase_admin_initialized = True
            print("Firebase Admin SDK initialized successfully.")
        except Exception as e_init:
            print(f"ERROR: Could not initialize Firebase Admin SDK from __firebase_config: {e_init}. Firestore features will be disabled.")
    else:
        print("WARNING: __firebase_config not found. Running without Firebase Admin SDK (Firestore features disabled for local testing).")
except ImportError:
    print("WARNING: firebase_admin not installed. Firestore features will be disabled.")
except Exception as e:
    print(f"ERROR: General exception during Firebase Admin SDK import/init: {e}. Firestore features will be disabled.")

_db = None
_auth = None
if _firebase_admin_initialized:
    _db = firestore.client()
    print("Firestore client initialized.")

# --- In-memory chat history for local development ---
_in_memory_chat_history = {}
# --- END NEW ---

load_dotenv()

app = Flask(__name__)
CORS(app)

FREE_TIER_API_KEY = os.environ.get("GOOGLE_API_KEY")
PAID_API_KEY = os.environ.get("GOOGLE_PAID_API_KEY")

if not FREE_TIER_API_KEY:
    print("CRITICAL ERROR: GOOGLE_API_KEY environment variable (free-tier) is not set or empty. Using dummy.")
    FREE_TIER_API_KEY = "dummy_free_key_for_test"
else:
    print(f"Loaded FREE_TIER_API_KEY. Length: {len(FREE_TIER_API_KEY)} (First 5 chars: {FREE_TIER_API_KEY[:5]})")

if not PAID_API_KEY:
    print("CRITICAL ERROR: GOOGLE_PAID_API_KEY environment variable is not set or empty. Exiting.")
    sys.exit("GOOGLE_PAID_API_KEY not found. Please set it in your .env file.")
else:
    print(f"Loaded PAID_API_KEY. Length: {len(PAID_API_KEY)} (First 5 chars: {PAID_API_KEY[:5]})")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))

try:
    from rag_query import get_response_from_rag
    print("Successfully imported get_response_from_rag from rag_query.py")
except ImportError as e:
    print(f"Error importing rag_query: {e}")
    print("Please ensure 'rag_query.py' is in the 'WeavingStories/scripts/' directory and contains a callable function named 'get_response_from_rag'.")
    print("Using dummy function for now.")

    # Dummy function must now return story AND admin_note
    def get_response_from_rag(chat_contents, chunk_store_path, embeddings_source_path, free_key, paid_key):
        last_user_message = ""
        if chat_contents and chat_contents[-1]['role'] == 'user' and chat_contents[-1]['parts']:
            last_user_message = chat_contents[-1]['parts'][0].get('text', '')
        return f"Dummy response: Query '{last_user_message}'", "Admin Note: Dummy response generated."


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHUNK_STORE_PATH = os.path.join(BASE_DIR, 'data', 'chunk_store_wiki_only.json')
EMBEDDINGS_SOURCE_PATH = os.path.join(BASE_DIR, 'data', 'chunks_for_embeddings_source.json')
ALL_PROCESSED_CHUNKS_PATH = os.path.join(BASE_DIR, 'data', 'all_processed_chunks.json')

_current_user_id = "anonymous"

@app.before_request
def set_local_user_id():
    global _current_user_id
    if _firebase_admin_initialized:
        _current_user_id = "canvas_user_placeholder"
    else:
        _current_user_id = "anonymous_local_user"


@app.route('/query_roman_empire', methods=['POST'])
def query_roman_empire():
    data = request.get_json()
    user_query = data.get('query')
    session_id = data.get('sessionId')

    if not user_query or not session_id:
        return jsonify({"error": "Query or Session ID not provided"}), 400

    try:
        current_chat_contents_for_gemini = []

        if _firebase_admin_initialized:
            app_id = "default-app-id-local"
            user_id = _current_user_id

            messages_ref = _db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('chat_sessions').document(session_id).collection('messages')
            
            docs = messages_ref.order_by('timestamp').get()
            chat_history_from_db = []
            for doc in docs:
                msg_data = doc.to_dict()
                # MODIFIED: Filter out admin_note when creating history for Gemini
                if 'role' in msg_data and 'text' in msg_data:
                    chat_history_from_db.append({'role': msg_data['role'], 'parts': [{'text': msg_data['text']}]})
            
            # Add current user query
            current_chat_contents_for_gemini = chat_history_from_db + [{'role': 'user', 'parts': [{'text': user_query}]}]

            # Store the user's message (as before)
            messages_ref.add({
                'role': 'user',
                'text': user_query,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'admin_note': None
            })
            
            print(f"DEBUG: Firestore chat history loaded for session {session_id}, total {len(chat_history_from_db)} previous turns.")

        else:
            global _in_memory_chat_history
            if session_id not in _in_memory_chat_history:
                _in_memory_chat_history[session_id] = []
            
            # Add current user query to in-memory history (with admin_note: None for consistency)
            _in_memory_chat_history[session_id].append({'role': 'user', 'parts': [{'text': user_query}], 'admin_note': None})

            # MODIFIED: When retrieving for Gemini, ensure only role and parts are sent
            chat_history_for_gemini_from_memory = []
            for msg_in_mem in _in_memory_chat_history[session_id]:
                chat_history_for_gemini_from_memory.append({'role': msg_in_mem['role'], 'parts': [{'text': msg_in_mem['parts'][0]['text']}]})
            
            current_chat_contents_for_gemini = chat_history_for_gemini_from_memory

            print(f"DEBUG: In-memory chat history loaded for session {session_id}, total {len(_in_memory_chat_history[session_id]) -1} previous turns.")


        # Call RAG logic
        roman_story, admin_note_from_rag = get_response_from_rag(
            current_chat_contents_for_gemini,
            CHUNK_STORE_PATH,
            EMBEDDINGS_SOURCE_PATH,
            FREE_TIER_API_KEY,
            PAID_API_KEY
        )

        if _firebase_admin_initialized:
            # Store model response WITH admin_note in Firestore
            messages_ref.add({
                'role': 'model',
                'text': roman_story,
                'admin_note': admin_note_from_rag, # NEW FIELD: Store the admin note
                'timestamp': firestore.SERVER_TIMESTAMP
            })
        else:
            # Store model response WITH admin_note in in-memory history
            _in_memory_chat_history[session_id].append({
                'role': 'model',
                'parts': [{'text': roman_story}],
                'admin_note': admin_note_from_rag # NEW FIELD: Store the admin note
            })

        return jsonify({"story": roman_story})

    except Exception as e:
        print(f"Error processing query: {e}")
        return jsonify({"error": f"Internal server error during RAG process. Check backend logs for details. Error: {type(e).__name__}"}), 500

if __name__ == '__main__':
    env_file_path = os.path.join(BASE_DIR, '.env')
    if not os.path.exists(env_file_path):
        print(f"Creating a placeholder .env file at {env_file_path}")
        print("Please add your GOOGLE_API_KEY=YOUR_API_KEY_HERE and GOOGLE_PAID_API_KEY=YOUR_PAID_API_KEY_HERE to this file.")
        with open(env_file_path, 'w') as f:
            f.write("GOOGLE_API_KEY=YOUR_GEMINI_API_KEY_HERE\n")
            f.write("GOOGLE_PAID_API_KEY=YOUR_PAID_GEMINI_API_KEY_HERE\n")

    app.run(debug=True, port=5001)