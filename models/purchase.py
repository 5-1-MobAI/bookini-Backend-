from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import AIMessage, HumanMessage, SystemMessage
import os
import requests
import json
import firebase_admin
from firebase_admin import credentials, firestore
from typing import Dict, List, Optional, Tuple
import re

# Load environment variables
load_dotenv()

# Initialize Firebase
cred = credentials.Certificate(os.getenv("FIREBASE_CREDENTIALS_PATH"))
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

# Initialize Google Generative AI
model = ChatGoogleGenerativeAI(
    model=os.getenv("GENAI_MODEL", "gemini-1.5-flash"),
    temperature=float(os.getenv("GENAI_TEMPERATURE", 0)),
    max_tokens=int(os.getenv("GENAI_MAX_TOKENS", 1024)),
    timeout=int(os.getenv("GENAI_TIMEOUT", 60)),
    max_retries=int(os.getenv("GENAI_MAX_RETRIES", 5)),
)

chat_history = []  # Use a list to store messages

# Initial system message (optional)
system_message = SystemMessage(content="You are a helpful AI assistant that helps users find and purchase books.")
chat_history.append(system_message)

def parse_user_request(request_text: str) -> Dict:
    """
    Use Gemini to parse the user's request and determine if it's a book purchase request.
    If it is, return a JSON object with quantity and topic. Otherwise, return None.
    """
    prompt = f"""Analyze this user request: '{request_text}'
    If the request is about buying books, respond with ONLY a valid JSON object in this exact format:
    {{"quantity": <number>, "topic": "<description>"}}
    
    Rules:
    - quantity must be a valid number (default to 1 if not specified).
    - if the request is not about buying books, set quantity to 0 and topic to "Null".
    - topic should be the search terms for the book (if applicable).
    - remove words like "buy me" or "get me" from the topic.
    - remove the quantity words from the topic.
    - handle typos in the query (in quantity and topic)
    
    Example inputs and outputs:
    Input: "buy me three books about dragons"
    Output: {{"quantity": 3, "topic": "dragons"}}
    
    
    Input: "hello"
    Output: {{"quantity": 0, "topic": "Null"}}
    """
    
    try:
        result = model.invoke(prompt)
        response_text = result.content.strip()
        print(f"Gemini response: {response_text}")  # Debug log
        
        # Clean the response if it's wrapped in Markdown code blocks
        if response_text.startswith("```json") and response_text.endswith("```"):
            response_text = response_text[7:-3].strip()  # Remove ```json and ```
        
        # Ensure we're parsing valid JSON
        try:
            parsed = json.loads(response_text)
            return parsed
        except json.JSONDecodeError:
            print("Error: Gemini returned invalid JSON. Using default values.")
            return {"quantity": 0, "topic": "Null"}  # Fallback to default values
            
    except Exception as e:
        print(f"Error in parse_user_request: {str(e)}")
        return {"quantity": 0, "topic": "Null"}  # Fallback to default values

def search_books(query: str) -> List[Dict]:
    """
    Search for books using the Gemini model and fetch details.
    """
    prompt = (
        f"You are a helpful book recommendation assistant. The user is looking for books about: '{query}'.\n\n"
        "Please provide a markdown table with two columns: 'Title' and 'Author'. "
        "Return only the table without any extra commentary. Give me 5 relevant books."
    )
    
    result = model.invoke(prompt)
    table_text = result.content.strip()
    
    # Parse the markdown table
    recommended_books = []
    lines = table_text.split('\n')
    if len(lines) >= 3:  # Has header, separator, and data
        for line in lines[2:]:  # Skip header and separator
            parts = [part.strip() for part in line.split('|') if part.strip()]
            if len(parts) >= 2:
                book_info = fetch_book_details(parts[0])  # Fetch details for each book
                if book_info:
                    recommended_books.append(book_info)
    
    return recommended_books

def fetch_book_details(title: str) -> Optional[Dict]:
    """
    Fetch book details from Google Books API.
    """
    url = f"https://www.googleapis.com/books/v1/volumes"
    params = {
        'q': title,
        'key': os.getenv("GOOGLE_BOOKS_API_KEY", "")
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        if "items" not in data:
            return None
        
        volume_info = data["items"][0].get("volumeInfo", {})
        sale_info = data["items"][0].get("saleInfo", {})
        
        details = {
            "title": volume_info.get("title", "N/A"),
            "author": ", ".join(volume_info.get("authors", [])) if volume_info.get("authors") else "N/A",
            "publisher": volume_info.get("publisher", "N/A"),
            "published_date": volume_info.get("publishedDate", "N/A"),
            "description": volume_info.get("description", "N/A"),
            "thumbnail": volume_info.get("imageLinks", {}).get("thumbnail", "N/A"),
            "categories": ", ".join(volume_info.get("categories", [])) if volume_info.get("categories") else "N/A",
            "price": get_price_info(sale_info)
        }
        return details
        
    except Exception as e:
        print(f"Error fetching book details: {str(e)}")
        return None

def get_price_info(sale_info: Dict) -> str:
    """Get price information from sale info."""
    if "listPrice" in sale_info:
        amount = sale_info["listPrice"].get("amount", "N/A")
        currency = sale_info["listPrice"].get("currencyCode", "")
        return f"{amount} {currency}".strip()
    return "N/A"

def handle_user_request(user_id: str, request_text: str) -> Dict:
    """
    Main function to handle user requests.
    If the request is about buying books, process it. Otherwise, respond normally.
    """
    parsed_request = parse_user_request(request_text)
    
    if parsed_request["quantity"] > 0 and parsed_request["topic"] != "Null":
        # This is a book purchase request
        quantity = parsed_request["quantity"]
        topic = parsed_request["topic"]
        
        # Search for books based on the topic
        found_books = search_books(topic)
        print(f"Found books: {found_books}")

        if not found_books:
            response = f"I couldn't find any books about '{topic}'. Please try a different topic."
            return {"message": response, "books": [], "purchase_details": []}
        
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
        return {
            "message": response,
            "requested_quantity": quantity,
            "requested_topic": topic,
            "found_books": filtered_books[:quantity],
            "purchase_details": purchase_details
        }
    else:
        # This is a normal conversation request
        result = model.invoke(request_text)
        response = result.content
        return {"message": response, "books": [], "purchase_details": []}
    

def test_purchase_function():
    """
    Test function to demonstrate the book purchase functionality
    """
    test_user_id = "test_user_123"
    while True:
        query = input("You: ")
        if query.lower() == "exit":
            break
        chat_history.append(HumanMessage(content=query))

        result = handle_user_request(test_user_id, query)
        response = result.get("message", "An error occurred while processing your request.")
        chat_history.append(AIMessage(content=response))
        print(f"AI: {response}")

        if result.get("found_books"):
            print("Here are the books I found:")
            for book in result["found_books"]:
                print(f"- {book['title']} by {book['author']}")

        if result.get("purchase_details"):
            print("\nPurchase Details:")
            print(json.dumps(result["purchase_details"], indent=2))

    print("---- Message History ----")
    print(chat_history)

if __name__ == "__main__":
    test_purchase_function()