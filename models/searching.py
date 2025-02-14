from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
import os
import requests
import json

# Load environment variables
load_dotenv()

# Initialize the ChatGoogleGenerativeAI model (your RAG LLM)
model = ChatGoogleGenerativeAI(
    model=os.getenv("GENAI_MODEL", "gemini-1.5-flash"),
    temperature=float(os.getenv("GENAI_TEMPERATURE", 0)),
    max_tokens=int(os.getenv("GENAI_MAX_TOKENS", 1024)),
    timeout=int(os.getenv("GENAI_TIMEOUT", 60)),
    max_retries=int(os.getenv("GENAI_MAX_RETRIES", 5)),
)

# Prompt the user for a description of the desired book
user_query = input("Enter a brief description of the book you want: ")

# Build a prompt for the model to return a markdown table of 5 book recommendations.
prompt = (
    f"You are a helpful book recommendation assistant. The user is looking for a book described as: '{user_query}'.\n\n"
    "Please provide a markdown table with two columns: 'Title' and 'Author'. "
    "Return only the table without any extra commentary. Give me 5 books."
)

# Generate the recommendations using the model
result = model.invoke(prompt)
table_text = result.content.strip()
# Parse the markdown table into a list of dictionaries.
lines = table_text.split('\n')
if len(lines) < 3:
    recommended_books = []
else:
    recommended_books = []
    for line in lines[2:]:
        # Split by '|' and remove empty strings and extra whitespace
        parts = [part.strip() for part in line.split('|') if part.strip()]
        if len(parts) >= 2:
            recommended_books.append({"title": parts[0], "author": parts[1]})

def fetch_book_details(title):
    """
    Given a book title, this function fetches details from the Google Books API.
    It returns a dictionary with Title, Author, Publisher, Published Date,
    Description, Thumbnail, Category, and Price.
    """
    url = f"https://www.googleapis.com/books/v1/volumes?q={title}"
    resp = requests.get(url)
    if resp.status_code == 200:
        data = resp.json()
        if "items" in data and len(data["items"]) > 0:
            volume_info = data["items"][0].get("volumeInfo", {})
            sale_info = data["items"][0].get("saleInfo", {})
            details = {
                "Title": volume_info.get("title", "N/A"),
                "Author": ", ".join(volume_info.get("authors", [])) if volume_info.get("authors") else "N/A",
                "Publisher": volume_info.get("publisher", "N/A"),
                "Published Date": volume_info.get("publishedDate", "N/A"),
                "Description": volume_info.get("description", "N/A"),
                "Thumbnail": volume_info.get("imageLinks", {}).get("thumbnail", "N/A"),
                "Category": ", ".join(volume_info.get("categories", [])) if volume_info.get("categories") else "N/A",
            }
            # Remove the model price verification. Simply set to "N/A" if not provided.
            if "listPrice" in sale_info:
                price_amount = sale_info["listPrice"].get("amount", "N/A")
                currency = sale_info["listPrice"].get("currencyCode", "")
                details["Price"] = f"{price_amount} {currency}".strip()
            else:
                details["Price"] = "N/A"
            return details
    return None

# Fetch detailed information for each recommended book
book_details_list = []
for book in recommended_books:
    details = fetch_book_details(book["title"])
    if details:
        book_details_list.append(details)

# Output the fetched book details in JSON format
if book_details_list:
    print(json.dumps(book_details_list, indent=2))