from flask import Flask, request, jsonify
import sys 
import os
import threading
from langchain_google_genai import ChatGoogleGenerativeAI
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from chat_storage import save_chat, get_chat_history
from models.recommender import main_recommender
from models.purchase import (
    handle_user_request, 
    get_chat_history, 
    save_chat,
    parse_user_request,
    search_books,
    fetch_book_details,
    get_price_info
)
from models.searching import main_search
from models.voice import main_voice
from flasgger import Swagger
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
if not firebase_admin._apps:  # Prevent reinitialization error
    cred = credentials.Certificate("FIREBASE_CREDENTIALS_PATH")
    firebase_admin.initialize_app(cred)

# Firestore client
db = firestore.client()

# Initialize Google Generative AI
model = ChatGoogleGenerativeAI(
    model=os.getenv("GENAI_MODEL", "gemini-1.5-flash"),
    temperature=float(os.getenv("GENAI_TEMPERATURE", 0)),
    max_tokens=int(os.getenv("GENAI_MAX_TOKENS", 1024)),
    timeout=int(os.getenv("GENAI_TIMEOUT", 60)),
    max_retries=int(os.getenv("GENAI_MAX_RETRIES", 5)),
)

app = Flask(__name__)
swagger = Swagger(app)
CORS(app)

## done
@app.route('/chat/save', methods=['POST'])
def save_chat_message():
    data = request.json
    user_id = data.get("user_id")
    message = data.get("message")
    role = data.get("role", "user")

    if not user_id or not message:
        return jsonify({"error": "Missing user_id or message"}), 400

    save_chat(user_id, message, role)
    return jsonify({"status": "success"})

## done
@app.route('/chat/history', methods=['GET'])
def get_chat():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    history = get_chat_history(user_id)
    return jsonify(history)



## recommender 
@app.route('/recommend', methods=['GET', 'POST'])
def recommend():
    try:
        if request.method == 'GET':
            user_id = request.args.get('user_id')
        elif request.method == 'POST':
            data = request.get_json()
            user_id = data.get('user_id')
        else:
            return jsonify({"error": "Invalid request method"}), 400

        if not user_id:
            return jsonify({"error": "User ID is required"}), 400

        recommendations = main_recommender(user_id)
        return jsonify({"user_id": user_id, "recommendations": recommendations})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

## the searching (done)
@app.route('/search', methods=['POST'])
def search():
    """
    Endpoint to search for books based on a query.
    """
    data = request.json
    query = data.get('query')

    if not query:
        return jsonify({"error": "Missing query"}), 400

    try:
        # Call the main_search function with the user's query
        books = main_search(query)
        if books:
            return jsonify({"books": books}), 200
        else:
            return jsonify({"error": "No books found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# purchasing and chat bot    
@app.route('/chat', methods=['POST'])
def chat():
    """
    API endpoint to handle user requests.
    """
    data = request.json
    user_id = data.get("user_id")
    message = data.get("message")

    if not user_id or not message:
        return jsonify({"error": "user_id and message are required"}), 400

    # Retrieve the chat history for the user
    chat_history = get_chat_history(user_id, limit=10)  # Adjust limit as needed

    # Add the new user message to the chat history
    save_chat(user_id, message, role="user")

    # Prepare the prompt with the chat history
    prompt = "\n".join([f"{msg['role']}: {msg['message']}" for msg in chat_history])
    prompt += f"\nuser: {message}"

    # Generate a response using the model
    result = model.invoke(prompt)
    response = result.content

    # Save the AI response to ChromaDB
    save_chat(user_id, response, role="assistant")

    # Parse the user's request (for book purchase logic)
    parsed_request = parse_user_request(message)

    if parsed_request["quantity"] > 0 and parsed_request["topic"] != "Null":
        # This is a book purchase request
        quantity = parsed_request["quantity"]
        topic = parsed_request["topic"]

        # Search for books based on the topic
        found_books = search_books(topic)
        print(f"Found books: {found_books}")

        if not found_books:
            response = f"I couldn't find any books about '{topic}'. Please try a different topic."
            save_chat(user_id, response, role="assistant")
            return jsonify({"message": response, "books": [], "purchase_details": []})

        # Get user details from Firebase
        user_ref = db.collection("users").document(user_id)
        user_data = user_ref.get().to_dict() or {}

        # Filter out books the user already owns
        filtered_books = [
            book for book in found_books
            if book["title"] not in user_data.get("owned_books", [])
        ]

        # Prepare purchase details for the requested quantity
        purchase_details = []
        for i in range(min(quantity, len(filtered_books))):
            book = filtered_books[i]
            purchase_details.append({
                "user_id": user_id,
                "book_title": book["title"],
                "author": book["author"],
                "price": book.get("price", "N/A"),
                "format": user_data.get("preferred_format", "Paperback"),
                "payment_method": user_data.get("default_payment", "Credit Card"),
                "shipping_address": user_data.get("default_address", "")
            })

        response = f"You can now go to the basket to confirm payment."
        save_chat(user_id, response, role="assistant")
        return jsonify({
            "message": response,
            "requested_quantity": quantity,
            "requested_topic": topic,
            "found_books": filtered_books[:quantity],
            "purchase_details": purchase_details
        })
    else:
        # This is a normal conversation request
        return jsonify({"message": response, "books": [], "purchase_details": []})

@app.route('/start-voice', methods=['GET'])
def start_voice():
    """API route to start the voice interaction in a separate thread"""
    thread = threading.Thread(target=main_voice)
    thread.start()
    return jsonify({"message": "Voice interaction started"}), 200


if __name__ == '__main__':
    app.run(debug=True)








